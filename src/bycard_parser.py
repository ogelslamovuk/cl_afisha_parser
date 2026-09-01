from contextlib import contextmanager
import ipaddress
import re
import socket
import threading
import time
from urllib.parse import parse_qs, urljoin, urlparse

import requests

from src.logger import log_info


class SourceFetchError(RuntimeError):
    pass


_VERIFICATION_COOKIE_RE = re.compile(r"hg-security=([^;\"']+)")
_DNS_OVERRIDE_LOCK = threading.Lock()


@contextmanager
def _resolve_host_to_ip(host, ip):
    """Temporarily pin one hostname inside this single-threaded process."""
    original_getaddrinfo = socket.getaddrinfo

    def pinned_getaddrinfo(query_host, port, *args, **kwargs):
        if query_host == host:
            query_host = ip
        return original_getaddrinfo(query_host, port, *args, **kwargs)

    with _DNS_OVERRIDE_LOCK:
        socket.getaddrinfo = pinned_getaddrinfo
        try:
            yield
        finally:
            socket.getaddrinfo = original_getaddrinfo


def _extract_from_nuxt(nuxt, base_url):
    events = []
    data0 = ((nuxt or {}).get("data") or [{}])[0]
    objects = data0.get("objects") or {}
    rows = objects.get("data") or []
    for row in rows:
        jsonlds = row.get("jsonld") or []
        for j in jsonlds:
            if j.get("@type") != "ScreeningEvent":
                continue
            event_url = j.get("url") or row.get("url")
            event_url = urljoin(base_url, event_url) if event_url else None
            sid = None
            if event_url:
                sid_values = parse_qs(urlparse(event_url).query).get("sid")
                sid = sid_values[0] if sid_values else None
            events.append({
                "sid": sid,
                "raw_event_url": event_url,
                "event_name": j.get("name") or row.get("name"),
                "startDate": j.get("startDate"),
                "location": j.get("location"),
                "object_id": row.get("id"),
                "object_name": row.get("name"),
                "object_address": (row.get("address") or {}).get("streetAddress") if isinstance(row.get("address"), dict) else row.get("address"),
                "image_candidates": [j.get("image"), row.get("image"), row.get("poster")],
                "price_candidates": [j.get("offers"), row.get("price"), row.get("prices")],
                "metadata": {"row": row, "jsonld": j},
            })
    last_page = objects.get("last_page") or 1
    return events, int(last_page) if str(last_page).isdigit() else 1


class _ApiClient:
    def __init__(
        self,
        timeout_seconds=45,
        connect_timeout_seconds=10,
        retries=2,
        retry_delay_seconds=1.0,
        max_response_bytes=30 * 1024 * 1024,
        fallback_ips=None,
    ):
        self.timeout = (
            max(1.0, float(connect_timeout_seconds)),
            max(1.0, float(timeout_seconds)),
        )
        self.retries = max(0, int(retries))
        self.retry_delay_seconds = max(0.0, float(retry_delay_seconds))
        self.max_response_bytes = max(1024, int(max_response_bytes))
        if isinstance(fallback_ips, str):
            fallback_ips = [fallback_ips]
        self.fallback_ips = []
        for value in fallback_ips or []:
            ip = str(ipaddress.ip_address(str(value)))
            if ip not in self.fallback_ips:
                self.fallback_ips.append(ip)
        self._sessions = {}
        self._route_selected = False
        self._preferred_ip = None

    @staticmethod
    def _new_session():
        session = requests.Session()
        session.headers.update({
            "Accept": "application/json, text/plain, */*",
            "User-Agent": "cl_afisha_parser/1.0",
        })
        return session

    def _get_session(self, resolve_ip):
        if resolve_ip not in self._sessions:
            self._sessions[resolve_ip] = self._new_session()
        return self._sessions[resolve_ip]

    @staticmethod
    def _is_json(response):
        content_type = response.headers.get("Content-Type", "").lower()
        return "application/json" in content_type

    @staticmethod
    def _verification_cookie(response):
        content_type = response.headers.get("Content-Type", "").lower()
        if "text/html" not in content_type:
            return None
        match = _VERIFICATION_COOKIE_RE.search(response.text)
        return match.group(1) if match else None

    def _get(self, session, url, params, resolve_ip):
        host = urlparse(url).hostname
        if resolve_ip:
            with _resolve_host_to_ip(host, resolve_ip):
                response = session.get(url, params=params, timeout=self.timeout, stream=True)
        else:
            response = session.get(url, params=params, timeout=self.timeout, stream=True)
        try:
            response.raise_for_status()
        except requests.RequestException:
            response.close()
            raise
        return self._read_bounded_response(response)

    def _read_bounded_response(self, response):
        chunks = []
        total = 0
        try:
            for chunk in response.iter_content(chunk_size=65536):
                if not chunk:
                    continue
                chunks.append(chunk)
                total += len(chunk)
                if total > self.max_response_bytes:
                    raise SourceFetchError(
                        f"API response exceeded max_response_bytes={self.max_response_bytes}"
                    )
            response._content = b"".join(chunks)
            response._content_consumed = True
            return response
        finally:
            response.close()

    def _request_with_verification(self, url, params, resolve_ip=None):
        session = self._get_session(resolve_ip)
        response = self._get(session, url, params, resolve_ip)
        response.raise_for_status()
        if self._is_json(response):
            return response

        token = self._verification_cookie(response)
        if not token:
            content_type = response.headers.get("Content-Type", "unknown")
            raise SourceFetchError(f"API returned unexpected content type: {content_type}")

        host = urlparse(url).hostname
        session.cookies.set("hg-security", token, domain=host, path="/")
        response = self._get(session, url, params, resolve_ip)
        response.raise_for_status()
        if not self._is_json(response):
            raise SourceFetchError("API verification repeated after cookie refresh")
        return response

    def get_json(self, url, params):
        last_error = None
        routes = [None, *self.fallback_ips]
        if self._route_selected:
            routes.remove(self._preferred_ip)
            routes.insert(0, self._preferred_ip)

        for attempt in range(self.retries + 1):
            for resolve_ip in routes:
                try:
                    response = self._request_with_verification(url, params, resolve_ip)
                    payload = response.json()
                    if not isinstance(payload, dict):
                        raise SourceFetchError("API JSON root must be an object")
                    route_changed = not self._route_selected or resolve_ip != self._preferred_ip
                    self._route_selected = True
                    self._preferred_ip = resolve_ip
                    if resolve_ip and route_changed:
                        log_info("fetch", f"api_route=fallback ip={resolve_ip}")
                    return payload
                except (requests.RequestException, ValueError, SourceFetchError, MemoryError) as exc:
                    last_error = exc
                    route = f"fallback ip={resolve_ip}" if resolve_ip else "primary"
                    message = str(exc).strip() or exc.__class__.__name__
                    log_info("fetch", f"{route} failed: {message}")
            if attempt < self.retries:
                time.sleep(self.retry_delay_seconds * (attempt + 1))
        message = str(last_error).strip() or last_error.__class__.__name__
        raise SourceFetchError(f"API request failed: {message}") from last_error


def _extract_api_page(payload, base_url):
    paginator = payload.get("data")
    if not isinstance(paginator, dict):
        raise SourceFetchError("API response is missing data paginator")
    if not isinstance(paginator.get("data"), list):
        raise SourceFetchError("API response is missing venue rows")

    # Keep the existing, proven JSON-LD extraction path. The API paginator is
    # the same `objects` structure that Nuxt previously embedded into the page.
    nuxt_compatible = {"data": [{"objects": paginator}]}
    return _extract_from_nuxt(nuxt_compatible, base_url)


def fetch_screening_events(config):
    src = config["source"]
    api_url = src["api_url"]
    base_url = src.get("start_url", "https://bycard.by/objects/minsk/2")
    per_page = int(src.get("per_page", 18))
    max_pages = int(src.get("max_pages", 20))
    params = {
        "filter[typeIds]": int(src.get("object_type_id", 2)),
        "filter[perPage]": per_page,
        "cityId": int(src.get("city_id", 3)),
        "jsonld": 1,
    }
    client = _ApiClient(
        timeout_seconds=src.get("timeout_seconds", 45),
        connect_timeout_seconds=src.get("connect_timeout_seconds", 10),
        retries=src.get("retries", 2),
        retry_delay_seconds=src.get("retry_delay_seconds", 1),
        max_response_bytes=src.get("max_response_bytes", 30 * 1024 * 1024),
        fallback_ips=src.get("fallback_ips", []),
    )

    all_events = []
    seen_sids = set()
    pages_scanned = 0
    page_number = 1
    last_page = 1

    while page_number <= last_page:
        if page_number > max_pages:
            raise SourceFetchError(f"API pagination exceeds max_pages={max_pages}")

        payload = client.get_json(api_url, {**params, "page": page_number})
        page_events, reported_last_page = _extract_api_page(payload, base_url)
        if page_number == 1:
            last_page = reported_last_page
            if last_page < 1:
                raise SourceFetchError("API reported invalid last_page")

        duplicate_count = 0
        for event in page_events:
            sid = event.get("sid")
            if sid and sid in seen_sids:
                duplicate_count += 1
                continue
            if sid:
                seen_sids.add(sid)
            all_events.append(event)

        pages_scanned += 1
        log_info(
            "fetch",
            f"page={page_number}/{last_page} rows={len(page_events)} duplicates={duplicate_count}",
        )
        page_number += 1

    if not all_events:
        raise SourceFetchError("API returned no ScreeningEvent entries")

    return all_events, pages_scanned
