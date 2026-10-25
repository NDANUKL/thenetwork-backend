"""Calendar schedules and safe, explicit recurring-plan transitions."""
from calendar import monthrange
from datetime import date, timedelta
import hashlib
import json
import re

FREQUENCIES = {'Monthly': 1, 'Every 3 months': 3}
OPEN_PLANS = ('Pending review', 'Active', 'Paused')
UNPREPARED = ('Scheduled', 'Awaiting access', 'Access confirmed')
TERMINAL = ('Completed', 'Skipped', 'Missed', 'Cancelled')
LEAD_DAYS = 14


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def day(value):
    try:
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',str(value)): raise ValueError()
        return date.fromisoformat(str(value))
    except (TypeError, ValueError):
        raise ValueError('Choose a valid date (YYYY-MM-DD)')


def add_months(anchor, months):
    year, month = divmod(anchor.year * 12 + anchor.month - 1 + months, 12)
    month += 1
    return date(year, month, min(anchor.day, monthrange(year, month)[1]))


def schedule(frequency, start_date=None, visits=None, dates=None, window_days=6, today=None):
    today = today or date.today()
    if isinstance(window_days, bool) or not isinstance(window_days, int) or not 0 <= window_days <= 14:
        raise ValueError('Choose a visit window of 0 to 14 days')
    if frequency == 'Specific dates':
        if isinstance(dates, str):
            try: dates = json.loads(dates)
            except ValueError: raise ValueError('Provide your agreed visit dates')
        if not isinstance(dates, list) or not 1 <= len(dates) <= 24:
            raise ValueError('Choose between 1 and 24 visit dates')
        result = sorted(day(value) for value in dates)
        if len(set(result)) != len(result): raise ValueError('Visit dates must be unique')
    elif frequency in FREQUENCIES:
        if isinstance(visits, bool) or not isinstance(visits, int) or not 1 <= visits <= 24:
            raise ValueError('Choose between 1 and 24 visits')
        first = day(start_date)
        result = [add_months(first, index * FREQUENCIES[frequency]) for index in range(visits)]
    else:
        raise ValueError('Choose monthly, every 3 months or specific dates')
    if result[0] < today or result[-1] + timedelta(days=window_days) > add_months(today, 24):
        raise ValueError('Visits must start today or later and finish within 24 months')
    if any(a + timedelta(days=window_days) >= b for a, b in zip(result, result[1:])):
        raise ValueError('Visit windows must not overlap')
    return [{'sequence': index, 'due_date': str(value), 'window_end': str(value + timedelta(days=window_days))}
            for index, value in enumerate(result, 1)]


def plan_transition(status, action, staff=False):
    transitions = {'Pause': {'Active': 'Paused'}, 'Resume': {'Paused': 'Active'},
        'Cancel': {value: 'Cancelled' for value in OPEN_PLANS}}
    if staff:
        transitions.update({'Approve': {'Pending review': 'Active'}, 'Decline': {'Pending review': 'Declined'}})
    target = transitions.get(action, {}).get(status)
    if not target: raise ValueError('This action is not available for the current plan status')
    return target


def can_prepare(plan_status, occurrence, today):
    return (plan_status == 'Active' and occurrence.get('status') == 'Access confirmed'
        and day(occurrence['due_date']) - timedelta(days=LEAD_DAYS) <= today <= day(occurrence['window_end'])
        and bool(occurrence.get('access_confirmed_at')) and not occurrence.get('request'))
