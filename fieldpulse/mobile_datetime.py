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
