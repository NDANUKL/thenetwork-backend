"""Task-specific brief contract and deterministic completeness checks.

No template catalogue, service inference, AI calls or evidence interpretation belongs
here. Approved content is pinned by digest; completeness never implies verification.
"""
import copy
import hashlib
import json
import math
import re
from datetime import datetime

CATEGORIES = {
    'land_property_check': 'Land and Property',
    'construction_progress': 'Construction Progress',
    'business_asset_check': 'Business and Asset',
    'custom_ground_verification': 'Custom Ground Verification',
}
RESPONSE_TYPES = {'text', 'single', 'multiple', 'none'}


def _text(value, label, limit=4000):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f'{label} must be nonempty text (up to {limit} characters)')
    return value.strip()


def validate_brief(raw):
    """Return a defensive copy; reject invalid AI output and coordinator edits alike."""
    brief = json.loads(raw) if isinstance(raw, str) else copy.deepcopy(raw)
    keys = {'schema_version', 'category', 'title', 'objective', 'scope', 'deliverables',
            'instructions', 'review_required', 'review_reasons', 'checks'}
    if not isinstance(brief, dict) or set(brief) != keys:
        raise ValueError('Task Brief has missing or unknown fields')
    if type(brief['schema_version']) is not int or brief['schema_version'] != 1:
        raise ValueError('Unsupported Task Brief schema version')
    if not isinstance(brief['category'], str) or brief['category'] not in CATEGORIES:
        raise ValueError('Choose one of the four service categories')
    for key in ('title', 'objective', 'scope'):
        brief[key] = _text(brief[key], key, 200 if key == 'title' else 4000)
    for key in ('deliverables', 'instructions', 'review_reasons'):
        values = brief[key]
        if not isinstance(values, list) or len(values) > 30:
            raise ValueError(f'{key} must be a list of up to 30 items')
        brief[key] = [_text(value, key, 2000) for value in values]
    if type(brief['review_required']) is not bool:
        raise ValueError('review_required must be a boolean')
    if brief['review_required'] != bool(brief['review_reasons']):
        raise ValueError('Review flags and reasons must agree')
    checks = brief['checks']
    if not isinstance(checks, list) or len(checks) > 50 or (not checks and not brief['review_required']):
        raise ValueError('Provide 1 to 50 checks, or flag the request for review')
    seen = set()
    for check in checks:
        if not isinstance(check, dict) or set(check) != {'id', 'instruction', 'response_type', 'options', 'required', 'evidence'}:
            raise ValueError('Invalid field check structure')
        identity = check['id']
        if not isinstance(identity, str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', identity) or identity in seen:
            raise ValueError('Field check IDs must be unique stable references')
        seen.add(identity)
        check['instruction'] = _text(check['instruction'], 'Check instruction', 2000)
        if not isinstance(check['response_type'], str) or check['response_type'] not in RESPONSE_TYPES or type(check['required']) is not bool:
            raise ValueError('Invalid response type or required flag')
        options = check['options']
        if not isinstance(options, list) or any(not isinstance(o, str) or not o.strip() or len(o) > 200 for o in options):
            raise ValueError('Invalid selection options')
        check['options'] = options = [o.strip() for o in options]
        if len(set(options)) != len(options):
            raise ValueError('Selection options must be unique')
        if check['response_type'] in {'single', 'multiple'}:
            if not 2 <= len(options) <= 30:
                raise ValueError('Selection checks need 2 to 30 options')
        elif options:
            raise ValueError('Only selection checks may have options')
        rules = check['evidence']
        if not isinstance(rules, list) or len(rules) > 2:
            raise ValueError('Specify photo and/or video requirements once per check')
        kinds = set()
        for rule in rules:
            if not isinstance(rule, dict) or set(rule) != {'kind', 'minimum', 'instruction'}:
                raise ValueError('Invalid evidence requirement')
            if not isinstance(rule['kind'], str) or rule['kind'] not in {'photo', 'video'} or rule['kind'] in kinds:
                raise ValueError('Evidence kinds must be photo or video without duplicates')
            kinds.add(rule['kind'])
            if type(rule['minimum']) is not int or not 1 <= rule['minimum'] <= 20:
                raise ValueError('Evidence minimum must be between 1 and 20')
            rule['instruction'] = _text(rule['instruction'], 'Evidence instruction', 1000)
        if check['response_type'] == 'none' and not rules:
            raise ValueError('An evidence-only check needs evidence requirements')
    return brief


def brief_digest(brief):
    canonical = json.dumps(validate_brief(brief), sort_keys=True, separators=(',', ':'), ensure_ascii=False)
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def assigned_brief(brief, check_ids):
    brief = validate_brief(brief)
    if not isinstance(check_ids, list) or not check_ids or any(not isinstance(i, str) for i in check_ids):
        raise ValueError('Assign at least one field check to this scout')
    if len(set(check_ids)) != len(check_ids) or not set(check_ids) <= {c['id'] for c in brief['checks']}:
        raise ValueError('Assigned checks contain duplicate or unknown references')
    brief['checks'] = [c for c in brief['checks'] if c['id'] in check_ids]
    return brief


def _number(value):
    return type(value) in (int, float) and math.isfinite(value)


def _timestamp(value):
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return parsed if parsed.tzinfo else None
    except (AttributeError, TypeError, ValueError):
        return None


def gps_result(point, site):
    """The pin, radius and accuracy threshold come from the approved assignment."""
    if not isinstance(point, dict) or not isinstance(site, dict):
        return {'status': 'invalid', 'distance_m': None}
    lat, lng, accuracy = (point.get(k) for k in ('latitude', 'longitude', 'accuracy_m'))
    slat, slng, radius, threshold = (site.get(k) for k in ('latitude', 'longitude', 'radius_m', 'accuracy_threshold_m'))
    if (not all(_number(v) for v in (lat, lng, accuracy, slat, slng, radius, threshold))
            or abs(lat) > 90 or abs(lng) > 180 or abs(slat) > 90 or abs(slng) > 180
            or accuracy < 0 or radius <= 0 or threshold <= 0 or not _timestamp(point.get('captured_at'))):
        return {'status': 'invalid', 'distance_m': None}
    a = math.sin(math.radians(lat - slat) / 2) ** 2 + math.cos(math.radians(lat)) * math.cos(math.radians(slat)) * math.sin(math.radians(lng - slng) / 2) ** 2
    distance = 6371000 * 2 * math.asin(min(1, math.sqrt(max(0, a))))
    status = 'inaccurate' if accuracy > threshold else 'outside' if distance > radius else 'inside'
    return {'status': status, 'distance_m': round(distance, 2)}


def evaluate_submission(brief, check_ids, submission, evidence, *, task_id, scout_id, site):
    """Evidence must be server-loaded upload records, never client-supplied claims.

    Callers must authenticate the scout, load the pinned brief/site and uploaded
    files, and enforce the submission lifecycle. This function performs no I/O.
    """
    brief = assigned_brief(brief, check_ids)
    errors, flags, summary = [], [], []
    answers = submission.get('answers', {})
    if not isinstance(answers, dict) or set(answers) - set(check_ids):
        raise ValueError('Answers must reference only this scout\'s assigned checks')
    if submission.get('declaration') is not True:
        errors.append('Confirm the final accuracy and evidence declaration')
    observations = submission.get('additional_observations', '')
    if not isinstance(observations, str) or len(observations) > 10000:
        errors.append('Additional observations must be text up to 10000 characters')
    arrival = submission.get('arrival') or {}
    arrival_status = gps_result(arrival, site)
    exception = submission.get('access_issue')
    if exception is not None:
        if not isinstance(exception, str) or not exception.strip() or len(exception) > 4000:
            errors.append('Access issue requires an explanation')
        if answers or evidence:
            errors.append('Access issues cannot submit completed field checks or evidence')
        # An unsafe approach is never required. Record available actual GPS, and
        # explicitly flag unavailable/inaccurate GPS for the coordinator.
        if arrival_status['status'] in {'invalid', 'inaccurate'}:
            flags.append('Access issue location is unavailable or inaccurate')
        return dict(complete=not errors, errors=errors, flags=flags, checks=[], status='access_issue', verified=False)
    if arrival_status['status'] != 'inside':
        errors.append('Verify arrival with accurate GPS before completing field checks')
    seen, files = set(), set()
    usable = {identity: [] for identity in check_ids}
    for item in evidence:
        identity = item.get('id')
        if not isinstance(identity, str) or not identity or identity in seen:
            errors.append('Evidence IDs must be unique')
            continue
        seen.add(identity)
        check_id = item.get('check_id')
        if item.get('task_id') != task_id or item.get('scout_id') != scout_id or check_id not in usable:
            errors.append('Evidence belongs to a different task, scout or check')
            continue
        if item.get('kind') not in {'photo', 'video'} or item.get('uploaded') is not True or not item.get('file_id'):
            errors.append('Evidence must reference an uploaded photo or video')
            continue
        if item['file_id'] in files:
            errors.append('A captured file may only count once in a submission')
            continue
        files.add(item['file_id'])
        point = gps_result(item, site)
        captured, arrived = _timestamp(item.get('captured_at')), _timestamp(arrival.get('captured_at'))
        sampled = _timestamp(item.get('location_sampled_at'))
        if item.get('source') != 'camera' or point['status'] != 'inside' or not captured or not sampled or abs((sampled-captured).total_seconds()) > 60 or not arrived or captured < arrived:
            flags.append(f'{identity}: capture source, time or GPS needs coordinator review')
            continue
        usable[check_id].append(item)
    for check in brief['checks']:
        identity = check['id']
        answer = answers.get(identity)
        missing = []
        if answer is None and not check['required']:
            summary.append(dict(id=identity, status='optional', missing=[]))
            continue
        if not isinstance(answer, dict):
            answer = {}
        if answer.get('status') == 'unable_to_verify':
            if not isinstance(answer.get('explanation'), str) or not answer['explanation'].strip() or len(answer['explanation']) > 4000:
                missing.append('Explain why this check could not be verified')
            status = 'unable_to_verify'
        else:
            status = 'complete'
            if answer.get('status') != 'observed':
                missing.append('Record the observation or select Unable to Verify')
            value, kind = answer.get('value'), check['response_type']
            if kind == 'text' and (not isinstance(value, str) or not value.strip() or len(value) > 10000):
                missing.append('Written observation required')
            if kind == 'single' and value not in check['options']:
                missing.append('Select one of the approved options')
            if kind == 'multiple' and (not isinstance(value, list) or not value or any(not isinstance(v, str) or v not in check['options'] for v in value) or len(set(value)) != len(value)):
                missing.append('Select valid, unique approved options')
            for rule in check['evidence']:
                count = sum(item['kind'] == rule['kind'] for item in usable[identity])
                if count < rule['minimum']:
                    missing.append(f"{rule['minimum']} {rule['kind']} capture(s) required; {count} usable")
        if missing:
            status = 'incomplete'
        summary.append(dict(id=identity, status=status, missing=missing))
        errors.extend(f'{identity}: {message}' for message in missing)
    return dict(complete=not errors, errors=errors, flags=flags, checks=summary, status='pending_coordinator_review', verified=False)
