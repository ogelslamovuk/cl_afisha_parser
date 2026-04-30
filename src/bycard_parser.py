from playwright.sync_api import sync_playwright
from urllib.parse import urlparse, parse_qs, urljoin
from src.logger import log_info


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


def fetch_screening_events(config):
    src = config["source"]
    all_events = []
    pages_scanned = 0
    with sync_playwright() as p:
        browser = p.firefox.launch(headless=bool(src.get("headless", True)))
        page = browser.new_page()
        page.set_default_timeout(int(src.get("timeout_seconds", 45) * 1000))

        start_url = src["start_url"]
        page.goto(start_url, wait_until="domcontentloaded")
        nuxt = page.evaluate("() => window.__NUXT__")
        page_events, last_page = _extract_from_nuxt(nuxt, start_url)
        all_events.extend(page_events)
        pages_scanned = 1
        log_info("fetch", f"page=1 rows={len(page_events)}")

        max_pages = int(src.get("max_pages", 20))
        end_page = min(last_page, max_pages)
        for n in range(2, end_page + 1):
            page_url = f"{start_url}?page={n}"
            page.goto(page_url, wait_until="domcontentloaded")
            nuxt = page.evaluate("() => window.__NUXT__")
            page_events, _ = _extract_from_nuxt(nuxt, start_url)
            all_events.extend(page_events)
            pages_scanned += 1
            log_info("fetch", f"page={n} rows={len(page_events)}")

        browser.close()
    return all_events, pages_scanned
