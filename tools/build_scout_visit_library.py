"""Publish the agreed visit workflow as v3 without rewriting v1/v2 source."""
import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
source = ROOT / 'fieldpulse/configuration/scout-questionnaires-v2.json'
data = copy.deepcopy(json.loads(source.read_text(encoding='utf-8')))
data.update(version=3, visit_workflow_version=2,
    policy_source='docs/scout-visit-workflow.md',
    policy_sha256=hashlib.sha256((ROOT / 'docs/scout-visit-workflow.md').read_bytes()).hexdigest())
videos = {
    'land':'Record a short overview of the plot, identifying features and current use.',
    'property':'Record one permitted overview of the building and assigned accessible areas; do not record people.',
    'construction':'Record one walkthrough covering the assigned milestones and work areas.',
    'business':'Record a permitted overview of the storefront and assigned goods or facilities. Do not record people, payment screens or transactions.',
    'vehicle':'Record an overview of the assigned vehicle and visible condition; demonstrate functions only when assigned.',
    'equipment':'Record an overview identifying the assigned present assets and their visible condition.',
    'delivery':'Record an overview of the received items and the labels needed to identify assigned specifications.',
}
for service in data['services']:
    for question in service['questions']:
        question.update(visit_workflow_version=2, visit_prompt=question['label'])
        for rule in question['evidence']:
            rule['caption'] = rule['subject'].split('.')[0]
            rule['detail_when'] = [answer for answer in rule.get('when', []) if not answer.lower().startswith(('no obvious','none')) and any(word in answer.lower() for word in ('issue','damage','deterioration','defect','difference'))]
    if service['service_code'] in videos:
        first = service['questions'][0]
        first['mandatory_selection'] = True
        first['evidence'].append(dict(id='visit-video',kind='Video',subject=videos[service['service_code']],
            caption=service['title'] + ' overview', once=True))
        service['description'] += '\n\nPhotos and an overview video are assigned evidence. If capture is prohibited, refused or unsafe, record a requirement-specific exception for coordinator review.'
target = ROOT / 'fieldpulse/configuration/scout-questionnaires-v3.json'
target.write_text(json.dumps(data, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print('Built v3 visit workflow; v1/v2 catalogues unchanged.')
