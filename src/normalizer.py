from datetime import datetime, timezone
from urllib.parse import urlparse
import html
import re


_EMPTY_VALUES = (None, "", [], {})
_CATEGORY_LABELS = {
    "kino": "Кино",
    "theatre": "Театр",
    "concert": "Концерт",
    "children": "Детям",
}


def _to_int(v):
    try:
        return int(v)
    except Exception:
        return None


def _clean_text(value):
    if not isinstance(value, str):
        return value
    # Bycard sometimes returns HTML entities and NBSP, for example
    # "Кинотеатр\xa0Аврора" or "&nbsp;" inside descriptions.
    value = html.unescape(value)
    value = value.replace("\u00a0", " ")
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def _clean_value(value):
    if isinstance(value, str):
        return _clean_text(value)
    if isinstance(value, list):
        cleaned = [_clean_value(v) for v in value]
        return [v for v in cleaned if v not in _EMPTY_VALUES]
    if isinstance(value, dict):
        return {k: _clean_value(v) for k, v in value.items()}
    return value


def _first_value(*values):
    for value in values:
        value = _clean_value(value)
        if value not in _EMPTY_VALUES:
            return value
    return None


def _walk_dicts(value, max_depth=5):
    if max_depth < 0:
        return
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from _walk_dicts(child, max_depth - 1)
    elif isinstance(value, list):
        for child in value:
            yield from _walk_dicts(child, max_depth - 1)


def _find_first(data, keys):
    key_set = {k.lower() for k in keys}
    for item in _walk_dicts(data):
        for key, value in item.items():
            if str(key).lower() in key_set:
                value = _clean_value(value)
                if value not in _EMPTY_VALUES:
                    return value
    return None


def _find_all(data, keys):
    key_set = {k.lower() for k in keys}
    found = []
    for item in _walk_dicts(data):
        for key, value in item.items():
            if str(key).lower() in key_set:
                value = _clean_value(value)
                if value not in _EMPTY_VALUES:
                    found.append(value)
    return found


def _to_string_list(value):
    value = _clean_value(value)
    if value in _EMPTY_VALUES:
        return None
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        for keys in (("name", "title", "label", "value"),):
            item = _first_value(*[value.get(k) for k in keys])
            if item:
                return [str(item)]
        return None
    if isinstance(value, list):
        out = []
        for item in value:
            values = _to_string_list(item)
            if values:
                out.extend(values)
        deduped = []
        for item in out:
            if item not in deduped:
                deduped.append(item)
        return deduped or None
    return None


def _to_number(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        text = value.replace("\u00a0", " ").replace(",", ".")
        m = re.search(r"\d+(?:\.\d+)?", text)
        if not m:
            return None
        num = float(m.group(0))
        return int(num) if num.is_integer() else num
    return None


def _extract_price_range(price_candidates):
    values = []
    low_values = []
    high_values = []
    low_keys = {"lowprice", "minprice", "min_price", "pricefrom", "from"}
    high_keys = {"highprice", "maxprice", "max_price", "priceto", "to"}
    price_keys = {"price", "amount", "value"}

    def scan(value):
        if value in _EMPTY_VALUES:
            return
        if isinstance(value, list):
            for item in value:
                scan(item)
            return
        if isinstance(value, dict):
            for key, child in value.items():
                normalized_key = str(key).lower()
                number = _to_number(child)
                if number is not None:
                    if normalized_key in low_keys:
                        low_values.append(number)
                    elif normalized_key in high_keys:
                        high_values.append(number)
                    elif normalized_key in price_keys:
                        values.append(number)
                scan(child)
            return
        number = _to_number(value)
        if number is not None:
            values.append(number)

    scan(price_candidates)
    all_values = values + low_values + high_values
    if not all_values:
        return None, None
    min_price = min(low_values or all_values)
    max_price = max(high_values or all_values)
    return min_price, max_price


def _extract_event_id(event_url):
    if not event_url:
        return None
    m = re.search(r"(\d+)(?:/?$)", urlparse(event_url).path)
    return _to_int(m.group(1)) if m else None


def _extract_category(event_url, row, jsonld):
    category = _first_value(
        _find_first(row, ("category", "categoryName", "category_name", "typeName", "type_name")),
        _find_first(jsonld, ("category", "genre", "eventType")),
    )
    if category:
        return category
    if event_url:
        parts = [p for p in urlparse(event_url).path.split("/") if p]
        if len(parts) >= 3 and parts[0] == "afisha":
            return _CATEGORY_LABELS.get(parts[2], parts[2])
    return None


def _extract_duration_minutes(row, jsonld):
    value = _first_value(
        _find_first(row, ("lengthInMinutes", "durationMinutes", "duration_minutes", "duration", "runtime", "runningTime")),
        _find_first(jsonld, ("duration",)),
    )
    if value is None:
        return None
    if isinstance(value, str):
        # ISO 8601 duration, for example PT1H35M.
        iso = re.fullmatch(r"P(?:T)?(?:(\d+)H)?(?:(\d+)M)?", value.strip(), re.IGNORECASE)
        if iso:
            hours = int(iso.group(1) or 0)
            minutes = int(iso.group(2) or 0)
            return hours * 60 + minutes
    return _to_int(_to_number(value))


def _extract_year(row, jsonld):
    value = _first_value(
        _find_first(row, ("productionYear", "production_year", "releaseYear", "release_year", "year")),
        _find_first(jsonld, ("productionYear", "datePublished", "copyrightYear")),
    )
    if isinstance(value, str):
        m = re.search(r"(?:19|20)\d{2}", value)
        return int(m.group(0)) if m else None
    return _to_int(value)


def normalize_events(raw_events):
    shows = []
    updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    for e in raw_events:
        metadata = e.get("metadata") if isinstance(e.get("metadata"), dict) else {}
        row = metadata.get("row") if isinstance(metadata.get("row"), dict) else {}
        jsonld = metadata.get("jsonld") if isinstance(metadata.get("jsonld"), dict) else {}

        sid = _clean_text(e.get("sid"))
        sid_int = _to_int(sid)
        show_url = f"https://saleframe.24afisha.by/?sid={sid}" if sid else None
        event_url = _clean_text(e.get("raw_event_url"))
        event_id = _extract_event_id(event_url)

        location = e.get("location") if isinstance(e.get("location"), dict) else {}
        theatre = _first_value(location.get("name"), e.get("object_name"))
        auditorium = _first_value(
            _find_first(row, ("theatreAuditorium", "auditorium", "hall", "hallName", "room", "screen")),
            _find_first(jsonld, ("auditorium", "room")),
        )
        theatre_and_auditorium = f"{theatre}, {auditorium}" if theatre and auditorium else theatre

        image = None
        for c in e.get("image_candidates") or []:
            c = _clean_value(c)
            if isinstance(c, str) and c.startswith("http"):
                image = c
                break
            if isinstance(c, dict):
                for _, val in c.items():
                    if isinstance(val, str) and val.startswith("http"):
                        image = val
                        break
            if image:
                break

        min_price, max_price = _extract_price_range(e.get("price_candidates") or [])
        genres = _to_string_list(_first_value(
            _find_first(row, ("genres", "genre", "genreNames", "genre_names")),
            _find_first(jsonld, ("genre",)),
        ))
        title = _first_value(e.get("event_name"), jsonld.get("name"), row.get("name")) or ""
        rating = _first_value(
            _find_first(row, ("rating", "age", "ageLimit", "age_limit", "ageRestriction")),
            _find_first(jsonld, ("typicalAgeRange", "contentRating")),
        )
        rating_label = _first_value(
            _find_first(row, ("ratingLabel", "rating_label", "ageLabel", "age_label")),
            rating,
        )

        seats_count = _to_int(_first_value(
            _find_first(row, ("seatsCount", "seats_count", "totalSeats", "total_seats", "capacity")),
            _find_first(jsonld, ("maximumAttendeeCapacity",)),
        ))
        busy_seats = _to_int(_find_first(row, ("busySeats", "busy_seats", "occupiedSeats", "occupied_seats")))

        show = {
            "title": title,
            "genres": genres,
            "images": {"eventLargeImagePortrait": image} if image else {"eventLargeImagePortrait": None},
            "rating": rating,
            "showId": sid_int,
            "eventId": event_id,
            "showUrl": show_url,
            "theatre": theatre,
            "category": _extract_category(event_url, row, jsonld),
            "eventUrl": event_url,
            "maxPrice": max_price,
            "minPrice": min_price,
            "promoter": _first_value(
                _find_first(row, ("promoter", "organizer", "organizerName", "seller", "provider")),
                _find_first(jsonld, ("organizer", "performer")),
            ),
            "busySeats": busy_seats,
            "theatreId": _to_int(e.get("object_id")),
            "updatedAt": updated_at,
            "seatsCount": seats_count,
            "description": _first_value(
                _find_first(row, ("description", "shortDescription", "short_description", "annotation", "text")),
                jsonld.get("description"),
            ),
            "haveTickets": "true" if sid_int else "false",
            "ratingLabel": rating_label,
            "dttmShowStart": _clean_text(e.get("startDate")),
            "originalTitle": title,
            "dtLocalRelease": _first_value(
                _find_first(row, ("dtLocalRelease", "localReleaseDate", "releaseDate", "release_date")),
                _find_first(jsonld, ("datePublished",)),
            ),
            "productionYear": _extract_year(row, jsonld),
            "lengthInMinutes": _extract_duration_minutes(row, jsonld),
            "theatreAuditorium": auditorium,
            "presentationMethod": _first_value(
                _find_first(row, ("presentationMethod", "presentation_method", "format", "formatName", "format_name")),
                _find_first(jsonld, ("videoFormat",)),
            ),
            "theatreAuditriumId": _to_int(_find_first(row, ("theatreAuditriumId", "theatreAuditoriumId", "auditoriumId", "hallId", "roomId"))),
            "theatreAndAuditorium": theatre_and_auditorium,
        }
        shows.append(_clean_value(show))

    return {"shows": shows}
