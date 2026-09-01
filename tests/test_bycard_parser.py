import unittest
from unittest.mock import patch

import requests

from src.bycard_parser import _ApiClient, fetch_screening_events
from src.writer import validate_shows


class _FakeCookies:
    def __init__(self):
        self.values = []

    def set(self, name, value, domain=None, path=None):
        self.values.append((name, value, domain, path))


class _FakeResponse:
    def __init__(self, content_type, text="", payload=None):
        self.headers = {"Content-Type": content_type}
        self.text = text
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload

    def iter_content(self, chunk_size=1):
        yield self.text.encode("utf-8")

    def close(self):
        return None


class _FakeSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.cookies = _FakeCookies()
        self.calls = []

    def get(self, url, params=None, timeout=None, stream=False):
        self.calls.append((url, params, timeout, stream))
        return self.responses.pop(0)


def _screening(sid, start="2026-08-03T12:00:00+03:00"):
    return {
        "@type": "ScreeningEvent",
        "name": "Test film",
        "image": "https://api.24afisha.by/uploads/events/test.jpg",
        "startDate": start,
        "url": f"https://bycard.by/afisha/minsk/kino/123?sid={sid}",
        "videoFormat": "2D",
        "location": {"name": "Test cinema"},
    }


def _page(page, last_page, events):
    return {
        "data": {
            "current_page": page,
            "last_page": last_page,
            "data": [{"id": 10, "name": "Test cinema", "jsonld": events}],
        }
    }


class ApiClientTests(unittest.TestCase):
    def test_verification_cookie_is_applied_before_json_retry(self):
        client = _ApiClient(retries=0)
        fake_session = _FakeSession([
            _FakeResponse(
                "text/html; charset=utf-8",
                '<script>document.cookie="hg-security=test-token; path=/"</script>',
            ),
            _FakeResponse("application/json", payload={"data": {}}),
        ])
        client._sessions[None] = fake_session
        client.session = fake_session

        result = client.get_json("https://api.24afisha.by/api/test", {"page": 1})

        self.assertEqual(result, {"data": {}})
        self.assertEqual(len(fake_session.calls), 2)
        self.assertEqual(
            fake_session.cookies.values,
            [("hg-security", "test-token", "api.24afisha.by", "/")],
        )

    def test_network_failure_switches_to_sticky_fallback(self):
        client = _ApiClient(retries=0, fallback_ips=["178.172.148.3"])
        json_response = _FakeResponse("application/json", payload={"data": {}})

        def request(url, params, resolve_ip=None):
            if resolve_ip is None:
                raise requests.ConnectTimeout("primary unavailable")
            return json_response

        with patch.object(client, "_request_with_verification", side_effect=request) as mocked:
            first = client.get_json("https://api.24afisha.by/api/test", {"page": 1})
            second = client.get_json("https://api.24afisha.by/api/test", {"page": 2})

        self.assertEqual(first, {"data": {}})
        self.assertEqual(second, {"data": {}})
        self.assertEqual(
            [call.args[2] for call in mocked.call_args_list],
            [None, "178.172.148.3", "178.172.148.3"],
        )

    def test_memory_error_switches_to_fallback(self):
        client = _ApiClient(retries=0, fallback_ips=["178.172.148.3"])
        json_response = _FakeResponse("application/json", payload={"data": {}})

        def request(url, params, resolve_ip=None):
            if resolve_ip is None:
                raise MemoryError()
            return json_response

        with patch.object(client, "_request_with_verification", side_effect=request) as mocked:
            result = client.get_json("https://api.24afisha.by/api/test", {"page": 1})

        self.assertEqual(result, {"data": {}})
        self.assertEqual([call.args[2] for call in mocked.call_args_list], [None, "178.172.148.3"])

    def test_oversized_response_switches_to_fallback(self):
        client = _ApiClient(retries=0, max_response_bytes=4, fallback_ips=["178.172.148.3"])
        primary = _FakeResponse("text/html", text="too large")
        fallback = _FakeResponse("application/json", text="{}", payload={"data": {}})

        client._sessions[None] = _FakeSession([primary])
        client._sessions["178.172.148.3"] = _FakeSession([fallback])

        result = client.get_json("https://api.24afisha.by/api/test", {"page": 1})

        self.assertEqual(result, {"data": {}})

    def test_dns_override_is_restored_after_request(self):
        from src.bycard_parser import _resolve_host_to_ip
        import socket

        original = socket.getaddrinfo
        with _resolve_host_to_ip("api.24afisha.by", "178.172.148.3"):
            self.assertIsNot(socket.getaddrinfo, original)
        self.assertIs(socket.getaddrinfo, original)


class FetchTests(unittest.TestCase):
    def test_all_pages_are_loaded_and_duplicate_sid_is_removed(self):
        class FakeClient:
            def __init__(self, **kwargs):
                pass

            def get_json(self, url, params):
                if params["page"] == 1:
                    return _page(1, 2, [_screening("101")])
                return _page(2, 2, [_screening("101"), _screening("102")])

        config = {
            "source": {
                "start_url": "https://bycard.by/objects/minsk/2",
                "api_url": "https://api.24afisha.by/api/v3/pages/objects",
                "city_id": 3,
                "object_type_id": 2,
                "per_page": 18,
                "max_pages": 20,
            }
        }

        with patch("src.bycard_parser._ApiClient", FakeClient):
            events, pages = fetch_screening_events(config)

        self.assertEqual(pages, 2)
        self.assertEqual([event["sid"] for event in events], ["101", "102"])


class ValidationTests(unittest.TestCase):
    def test_duplicate_show_id_and_invalid_link_are_rejected(self):
        show = {
            "showId": 1,
            "showUrl": "not-a-url",
            "eventUrl": "https://bycard.by/event/1",
            "title": "Film",
            "dttmShowStart": "2026-08-03T12:00:00+03:00",
            "theatreId": 10,
            "images": {"eventLargeImagePortrait": None},
        }
        valid, info = validate_shows(
            [show, dict(show)],
            {"validation": {"min_shows": 1, "min_theatres": 1, "min_distinct_dates": 1}},
        )

        self.assertFalse(valid)
        self.assertIn("duplicate showId count 1", info["errors"])
        self.assertTrue(any("invalid showUrl" in error for error in info["errors"]))


if __name__ == "__main__":
    unittest.main()
