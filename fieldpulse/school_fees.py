"""School fee policy overlay; historical published catalogues remain immutable."""
import copy

TITLE = "School fee payment confirmation"
LEGACY_TITLE = "University fee payment confirmation"

def apply_policy(data):
    data = copy.deepcopy(data)
    for service in data['services']:
        if service['service_code'] != 'university_fees':
            continue
        service['title'] = TITLE
        service['questionnaire_version'] = data['version'] + 3
        service['description'] = ("School fee payment verification for students of all ages. "
            "Required authorisation and institutional permission must be recorded. "
            "Check payment records only; no student contact, observation, attendance or enrolment checks.")
        for question in service['questions']:
            question['detail'] = question.get('detail', '').replace('university office', 'school or institution accounts office')
    return data
