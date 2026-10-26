"""Normalize mobile ISO timestamps to naive Frappe site-local datetimes."""
from datetime import datetime
from zoneinfo import ZoneInfo


def mobile_datetime(value, timezone_name=None):
    if value is None or value == "":
        return None
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            if timezone_name is None:
                from frappe.utils import get_system_timezone
                timezone_name = get_system_timezone()
            parsed = parsed.astimezone(ZoneInfo(timezone_name)).replace(tzinfo=None)
        return parsed
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError("Invalid mobile timestamp; expected an ISO 8601 datetime") from exc


def site_datetime_iso(value, timezone_name=None):
    """Label outbound site-local timestamps so a phone never guesses its timezone."""
    if value is None or value == "":
        return None
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if timezone_name is None:
            from frappe.utils import get_system_timezone
            timezone_name = get_system_timezone()
        zone = ZoneInfo(timezone_name)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=zone)
        return parsed.astimezone(zone).isoformat()
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError("Invalid site timestamp; expected an ISO 8601 datetime") from exc
