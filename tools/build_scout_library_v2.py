"""Build the versioned catalogue from the retained owner source and explicit rules.

Run only when intentionally publishing a new source revision. Never rewrites v1.
"""
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'docs/scout-questionnaire-library.md'
text = SOURCE.read_text(encoding='utf-8')
old = json.loads((ROOT / 'fieldpulse/configuration/scout-questionnaires.json').read_text())

MATCH = ['Matches', 'Partly matches', 'Does not match', 'Unable to confirm']
CONDITION = ['No obvious visible issues', 'Visible issues observed', 'Unable to inspect']
DEMO = ['Demonstrated without an obvious issue', 'Demonstrated with an issue', 'Not demonstrated']
RECORD = ['Matching record found', 'Record found with differences', 'No matching record found', 'Unable to obtain confirmation']
FIELDS = ['Matches', 'Differs', 'Not confirmed']

def q(options=None, kind='single', **kw):
    return dict(answer_type=kind, result_options=options or [], **kw)

def photo(subject, when=None):
    return dict(id='photo', kind='Photo', subject=subject, **({'when': when} if when else {}))

def demo():
    return q(DEMO, 'checklist', assigned_only=True, text_when=DEMO[1:], evidence=[dict(id='video', kind='Video', subject='Record the assigned function and its result. One clear clip may cover several functions.', when=DEMO[:2])])

specs = [
    [q(MATCH, text_required=True, evidence=[photo('Plot overview and the identifying or boundary features used in the answer.')]),
     q(['Appears vacant or unused', 'Buildings or structures', 'Construction', 'Farming or cultivation', 'Business activity', 'Other occupation or use', 'Unable to establish'], 'multi', text_required=True, evidence=[photo('Show the selected use or apparently vacant plot. Reuse an existing overview if clear.')]),
     q(kind='text', evidence=[photo('Show the entrance/access point and any reported obstruction.')])],
    [q(MATCH, text_when=MATCH[1:3], evidence=[photo('Exterior overview showing the building and relevant identifying features.')]),
     q(CONDITION, 'checklist', text_when=[CONDITION[1]], evidence=[photo('Overview of each inspected area; close-up of issues unless already clear.', CONDITION[:2])], walkthrough=True),
     q(['Signs observed', 'No signs observed during the visit', 'Unable to establish'], text_required=True),
     q(['Present', 'Not found', 'Unable to check'], 'checklist', text_when=['Not found'], demonstration=True, evidence=[photo('Show the requested items found. Existing area photos may cover several items.', ['Present'])])],
    [q(['Not started', 'In progress', 'Appears complete', 'Unable to assess'], 'checklist', text_required=True, evidence=[photo('Show each assessable milestone or its assigned work area.', ['Not started', 'In progress', 'Appears complete'])], walkthrough=True),
     q(['Visible progress', 'No visible change', 'Deterioration or removal', 'Unable to compare'], assigned_only=True, previous_required=True, text_required=True, evidence=[photo('Show the compared milestone/work area and reported changes; reuse milestone photos.', ['Visible progress', 'No visible change', 'Deterioration or removal'])]),
     q(['Yes', 'None beyond the milestone findings already recorded', 'Unable to assess'], text_when=['Yes'], evidence=[photo('Show each reported unfinished work, damage or apparent defect.', ['Yes'])]),
     q(kind='text'), q(['Representative confirmed', 'No representative available or willing to confirm'], assigned_only=True, source_required=True, text_when=['Representative confirmed'])],
    [q(['Present, open and operating', 'Present and open, but no activity observed', 'Present but closed', 'Business not found', 'Unable to confirm'], difference_optional=True, evidence=[photo('Storefront and signage, or assigned location if not found. Reuse the opening photo if sufficient.')]),
     q(['Observed available', 'Reported available but not observed', 'Not available', 'Unable to check'], 'checklist', condition=True, quantities=True, evidence=[photo('Show the goods or service facilities physically inspected, including any reported damage.', ['Observed available'])]),
     q(['No obvious visible issues', 'Visible issues', 'Unable to inspect'], text_when=['Visible issues'], evidence=[photo('Show each reported premises or equipment issue.', ['Visible issues'])]),
     q(['Answered', 'No representative available or willing to answer'], kind='interview', text_when=['Answered'], assigned_only=True, source_required=True)],
    [q(['Matches', 'Differs', 'Unable to check'], 'checklist', text_when=['Differs'], evidence=[photo('Vehicle overview and readable images of the assigned accessible identifiers.', ['Matches', 'Differs'])]),
     q(CONDITION, 'checklist', default_items=['Exterior: front, rear and both sides', 'Interior overview', 'Dashboard'], text_when=[CONDITION[1]], readings=True, evidence=[photo('Show the assigned vehicle section/views and close-ups of issues not already clear.', CONDITION[:2])]), demo()],
    [q(['Present', 'Not found', 'Unable to check'], 'checklist', identifier=True, quantities=True, evidence=[photo('Show each present asset and its assigned accessible identifier; group images are permitted.', ['Present'])]),
     q(['No obvious visible issues', 'Visible damage or deterioration', 'Unable to assess'], 'checklist', text_when=['Visible damage or deterioration'], evidence=[photo('Show each reported asset issue; reuse asset images if clear.', ['Visible damage or deterioration'])]), demo()],
    [q(['Confirmed', 'Unable to confirm'], 'checklist', source_required=True, confirmed_detail=True), q(['Matches', 'Partly matches', 'Does not match', 'Unable to establish'], text_when=['Partly matches', 'Does not match'], confirmation=True)],
    [q(RECORD, source_required=True), q(FIELDS, 'checklist', text_when=['Differs'], confirmation=True, record_gate=True)],
    [q(['Confirmed', 'Institution unable or unwilling to confirm'], text_when=['Confirmed'], source_required=True), q(['Fully', 'Partly', 'No', 'Unable to establish'], text_when=['Partly', 'No', 'Unable to establish'], confirmation=True)],
    [q(RECORD, source_required=True), q(FIELDS, 'checklist', text_when=['Differs'], confirmation=True, record_gate=True)],
    [q(['Matches', 'Differs', 'Missing or unreadable', 'Unable to check'], 'checklist', text_when=['Differs'], inspection=True),
     q(['Matching record confirmed', 'Record found with differences', 'No matching record reported', 'Issuer unable or unwilling to confirm', 'Issuer could not be reached'], assigned_only=True, source_required=True, confirmation=True)],
    [q(['Matching record found', 'Record found with differences', 'No matching record found', 'Issuer unable or unwilling to confirm', 'Issuer could not be reached'], source_required=True), q(FIELDS, 'checklist', text_when=['Differs'], confirmation=True, record_gate=True)],
    [q(['Present as ordered', 'Present with a difference', 'Missing', 'Unable to check'], 'checklist', quantities=True, quantity_required=True, text_when=['Present with a difference'], evidence=[photo('Show present items and labels needed to identify assigned models/specifications.', ['Present as ordered', 'Present with a difference'])]),
     q(['No obvious visible issues', 'Item damaged', 'Packaging damaged', 'Both damaged', 'Unable to inspect'], 'checklist', text_when=['Item damaged', 'Packaging damaged', 'Both damaged'], evidence=[photo('Show each reported item or packaging issue.', ['Item damaged', 'Packaging damaged', 'Both damaged'])]),
     q(['Confirmed', 'Unable to confirm'], 'checklist', assigned_only=True, confirmed_detail=True, source_required=True, delivery_document=True), demo()],
    [q(['Checked', 'Unable to check', 'Not applicable'], 'custom', custom_required=True, text_when=['Checked'])],
    [q(['Eligible and agreed', 'Eligible but declined', 'Not eligible', 'Unable to establish eligibility']),
     q(['Recorded', 'Unable to check'], 'checklist', confirmed_detail=True),
     q(['Reported', 'Observed', 'Reported and observed', 'Unable to check'], 'checklist', optional_verification=True),
     q(['Answered', 'Declined to answer', 'Unable to check'], 'interview', text_when=['Answered'])],
]

sections = re.split(r'^## (\d+)\. ', text.split('# Service questionnaires', 1)[1].split('## D. Closing', 1)[0], flags=re.M)
services = []
for i in range(1, len(sections), 2):
    number, body = int(sections[i]), sections[i+1]
    title = body.splitlines()[0]
    parts = re.split(r'^### (?:\d+\. |For each assigned question\s*$)', body, flags=re.M)[1:]
    if len(parts) != len(specs[number-1]):
        raise ValueError((number, len(parts), len(specs[number-1])))
    questions = []
    for index, (part, rules) in enumerate(zip(parts, specs[number-1]), 1):
        label = part.splitlines()[0].strip() if number != 14 else 'Coordinator-approved custom questions'
        rules = dict(rules)
        rules.setdefault('evidence', [])
        if rules['answer_type'] in ('single', 'checklist', 'multi', 'interview', 'custom') and not any(re.search(r'unable|not demonstrated|declined', o, re.I) for o in rules['result_options']):
            rules['result_options'].append('Unable to check')
        questions.append(dict(code=f'{number}.{index}', label=label, detail=part.strip() if number != 14 else part.strip(), **rules))
    services.append(dict(number=number, title=title, description=body.split('###', 1)[0].split('\n', 1)[1].strip(), service_code=old['services'][number-1]['service_code'], questions=questions, authorisation_required=number in (7, 8, 9, 10)))

data = dict(source='docs/scout-questionnaire-library.md', source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(), version=2, protocol_version=2, services=services)
(ROOT / 'fieldpulse/configuration/scout-questionnaires-v2.json').write_text(json.dumps(data, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(f'Built {len(services)} services, {sum(len(s["questions"]) for s in services)} question definitions')
