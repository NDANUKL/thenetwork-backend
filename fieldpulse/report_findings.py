"""Readable, factual report text from approved answers; no invented conclusions."""
import json


def decode(value, fallback):
    try: return json.loads(value) if isinstance(value, str) else value or fallback
    except (ValueError, TypeError): return fallback


def readable(value):
    if isinstance(value, bool): return 'Yes' if value else 'No'
    if isinstance(value, list): return '; '.join(readable(item) for item in value)
    if isinstance(value, dict): return '; '.join(f'{key.replace("_", " ").capitalize()}: {readable(item)}' for key, item in value.items() if item not in (None, ''))
    return str(value) if value is not None else ''


def finding_text(question, raw, all_answers, fallback=''):
    answer = decode(raw, {})
    if not isinstance(answer, dict): return readable(answer) or fallback, []
    config = decode(question.get('validation_json'), {})
    labels = {item['id']: item['label'] for item in config.get('items', [])}
    lines, limitations = [], []
    fields = [('result', 'Result'), ('results', 'Results'), ('text', 'Finding'),
        ('source_type', 'Source type'), ('source_role', 'Confirming office / role'),
        ('source', 'Attributed source and statement'), ('quantity', 'Quantity'),
        ('reading', 'Reading'), ('condition', 'Condition'), ('identifier', 'Identifier'),
        ('demonstration', 'Demonstration'), ('concern_details', 'Concern and location')]
    def render(value):
        result = [f'{label}: {readable(value[key])}' for key, label in fields if value.get(key) not in (None, '', [])]
        if value.get('explanation_ref'):
            explanation = decode(all_answers.get(value['explanation_ref']), {})
            if not isinstance(explanation, dict): explanation = {}
            result.append('Explanation: ' + readable(explanation.get('text') or explanation.get('explanation') or 'Referenced explanation unavailable'))
        if value.get('explanation'): result.append('Explanation / follow-up: ' + readable(value['explanation']))
        return result
    if answer.get('blocked'): lines.append('Unable to check')
    lines.extend(render(answer))
    if not answer.get('blocked'):
        for identity, item in (answer.get('items') or {}).items():
            lines.append(labels.get(identity, identity.replace('_', ' ').capitalize()) + '\n' + ('\n'.join(render(item)) if isinstance(item, dict) else readable(item)))
    for identity, exception in (answer.get('exceptions') or {}).items():
        # Evidence requirement IDs remain in the internal source, not the client narrative.
        reason = readable(exception)
        limitations.append('Evidence unavailable: ' + reason)
    if answer.get('media_unavailable_reason'): limitations.append('Evidence limitation: ' + readable(answer['media_unavailable_reason']))
    if answer.get('explanation'): limitations.append(readable(answer['explanation']))
    return '\n'.join(lines) or fallback or 'No written finding recorded.', limitations
