"""Pure validation shared by submission and coordinator review. No client status is trusted."""
import json
import math
from fieldpulse.geofence import effective_geofence_radius


def parsed(value, fallback=None):
    try: return json.loads(value) if isinstance(value, str) else value
    except (TypeError, ValueError): return fallback


def arrival_result(arrival, location):
    arrival = parsed(arrival, {}) or {}
    try:
        lat, lng, accuracy = [float(arrival[key]) for key in ("latitude", "longitude", "accuracy_m")]
        site_lat, site_lng = float(location["latitude"]), float(location["longitude"])
        site_radius = float(location.get("geofence_radius_m") or 50)
        radius = effective_geofence_radius(site_radius)
        if not all(math.isfinite(v) for v in [lat, lng, accuracy, site_lat, site_lng, radius]) or abs(lat) > 90 or abs(lng) > 180 or accuracy < 0 or site_radius <= 0:
            raise ValueError()
        radians = math.pi / 180
        a = math.sin((lat-site_lat)*radians/2)**2 + math.cos(lat*radians)*math.cos(site_lat*radians)*math.sin((lng-site_lng)*radians/2)**2
        distance = 6371000 * 2 * math.asin(min(1, math.sqrt(a)))
        status = "Inside" if distance <= radius and accuracy <= site_radius else "Outside" if distance > radius else "Insufficient accuracy"
        if not arrival.get("captured_at"): status = "Invalid GPS"
        return dict(status=status, distance_m=round(distance, 2), site_latitude=site_lat, site_longitude=site_lng,
            radius_m=radius, latitude=lat, longitude=lng, accuracy_m=accuracy, captured_at=arrival.get("captured_at"))
    except (ValueError, TypeError, KeyError):
        return {"status": "Invalid GPS", "site_latitude": location.get("latitude"), "site_longitude": location.get("longitude"), "radius_m": location.get("geofence_radius_m") or 50}


def answer_issues(question, answer, evidence):
    config = parsed(question.get("validation_json"), {}) or {}
    if config.get("group") == "final": return []
    code = question["question_code"]
    prefix = code + ": "
    if not isinstance(answer, dict) or not answer.get("result"): return [prefix + "response missing"]
    result, text = answer["result"], str(answer.get("text") or "").strip()
    options = config.get("result_options") or ["Observed", "Confirmed", "Partly confirmed", "Not confirmed", "Unable to check", "Not applicable", "No information source"]
    issues = []
    if result not in options: issues.append(prefix + "invalid result")
    requires_text = code in {"S1", "S2"} or (code not in {"S3", "S4"}) or result in {"Some checks not completed", "No assigned checks completed"}
    if requires_text and not text: issues.append(prefix + "finding or exception explanation missing")
    if result in {"Unable to check", "Not applicable", "No information source"} and not str(answer.get("explanation") or "").strip():
        issues.append(prefix + "explanation and follow-up needed")
    if (code == "S3" and result == "Yes") or answer.get("information_source"):
        if not str(answer.get("source") or "").strip(): issues.append(prefix + "source role, statement and related question needed")
    if answer.get("concern"):
        if not str(answer.get("concern_details") or "").strip(): issues.append(prefix + "concern description and location needed")
        if not any(row.get("evidence_type") == "Photo" for row in evidence) and not str(answer.get("media_unavailable_reason") or "").strip():
            issues.append(prefix + "close-up or explanation needed")
    if config.get("demonstration_required") and answer.get("demonstration") not in {"Observed", "Not demonstrated", "Unable to check"}:
        issues.append(prefix + "demonstration result needed")
    if config.get("mandatory_evidence"):
        for kind in ("Photo", "Video"):
            if not any(row.get("evidence_type") == kind and str(row.get("caption") or "").strip() for row in evidence):
                issues.append(prefix + "mandatory " + kind.lower() + " and caption missing")
    return issues


def evaluate_submission(questions, answers, evidence, review, arrival, location=None):
    review = parsed(review, {}) or {}
    coverage = review.get("coverage")
    fatal = []
    if coverage not in {"Yes", "Partly", "No"}: fatal.append("Choose request coverage on the final review card")
    if coverage in {"Partly", "No"} and not str(review.get("additional_text") or "").strip():
        fatal.append("Explain outstanding checks, why they could not be completed, and follow-up needed")
    issues = []
    unresolved = False
    for question in questions:
        answer = parsed(answers.get(question["question_code"]), {}) or {}
        issues.extend(answer_issues(question, answer, evidence.get(question["question_code"], [])))
        if answer.get("result") in {"Unable to check", "Some checks not completed", "No assigned checks completed", "Location mismatch", "Unable to establish"}: unresolved = True
    if coverage == "Yes" and unresolved: fatal.append("An assigned check remains unresolved; choose Partly or No")
    if location is not None:
        for code, media in evidence.items():
            for item in media:
                if item.get("evidence_type") not in {"Photo", "Video"}: continue
                check = arrival_result(dict(latitude=item.get("gps_lat"), longitude=item.get("gps_lng"), accuracy_m=item.get("accuracy_m"), captured_at=item.get("captured_at")), location)
                if check["status"] != "Inside":
                    issues.append(f"{code}: {item.get('evidence_type')} capture location requires review: {check['status']}")
    if arrival.get("status") != "Inside": issues.append("Arrival location requires review: " + arrival.get("status", "Invalid GPS"))
    if issues and not (review.get("incomplete") is True and str(review.get("incomplete_reason") or "").strip()):
        fatal.append("Submission needs attention: " + "; ".join(issues) + ". Complete these checks, or use Send incomplete task for review and explain the issue.")
    reasons = list(issues)
    if arrival.get("exception_reason"):
        reasons.append("Arrival exception: " + str(arrival["exception_reason"]))
    for code in ("S1", "S2"):
        answer = parsed(answers.get(code), {}) or {}
        if answer.get("result") in {"Location mismatch", "Unable to establish", "Partial access", "No access"}:
            reasons.append(code + ": " + answer["result"])
    if coverage == "Partly": reasons.append("Client request partly addressed")
    if coverage == "No": reasons.append("Requested checks not completed")
    if review.get("incomplete"):
        if not str(review.get("incomplete_reason") or "").strip(): fatal.append("An incomplete submission needs a reason")
        reasons.append("Incomplete visit: " + str(review.get("incomplete_reason") or ""))
    return {"errors": fatal, "reasons": reasons, "status": "Needs review" if reasons else "Submitted for normal review"}
