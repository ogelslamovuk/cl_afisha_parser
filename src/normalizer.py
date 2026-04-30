from datetime import datetime, timezone
from urllib.parse import urlparse
import re


def _to_int(v):
    try:
        return int(v)
    except Exception:
        return None


def normalize_events(raw_events):
    shows = []
    updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    for e in raw_events:
        sid_int = _to_int(e.get("sid"))
        show_url = f"https://saleframe.24afisha.by/?sid={e.get('sid')}" if e.get("sid") else None
        event_url = e.get("raw_event_url")
        event_id = None
        if event_url:
            m = re.search(r"(\d+)(?:/?$)", urlparse(event_url).path)
            if m:
                event_id = _to_int(m.group(1))

        location = e.get("location") if isinstance(e.get("location"), dict) else {}
        theatre = location.get("name") or e.get("object_name")

        image = None
        for c in e.get("image_candidates") or []:
            if isinstance(c, str) and c.startswith("http"):
                image = c
                break
            if isinstance(c, dict):
                for _, val in c.items():
                    if isinstance(val, str) and val.startswith("http"):
                        image = val
                        break

        show = {
            "title": e.get("event_name") or "",
            "genres": None,
            "images": {"eventLargeImagePortrait": image} if image else {"eventLargeImagePortrait": None},
            "rating": None,
            "showId": sid_int,
            "eventId": event_id,
            "showUrl": show_url,
            "theatre": theatre,
            "category": None,
            "eventUrl": event_url,
            "maxPrice": None,
            "minPrice": None,
            "promoter": None,
            "busySeats": None,
            "theatreId": _to_int(e.get("object_id")),
            "updatedAt": updated_at,
            "seatsCount": None,
            "description": None,
            "haveTickets": "true" if sid_int else "false",
            "ratingLabel": None,
            "dttmShowStart": e.get("startDate"),
            "originalTitle": e.get("event_name") or "",
            "dtLocalRelease": None,
            "productionYear": None,
            "lengthInMinutes": None,
            "theatreAuditorium": None,
            "presentationMethod": None,
            "theatreAuditriumId": None,
            "theatreAndAuditorium": theatre,
        }
        shows.append(show)

    return {"shows": shows}
