"""Evidence lineage traversal, with document loading supplied by the caller."""

def evidence_origin_allowed(response, origin, get_doc):
    """Only the server-created correction ancestry may reuse an older capture."""
    if response == origin:
        return True
    target = get_doc('FP Task Response', response)
    seen = set()
    while target.get('rework_type') == 'Correct answers' and target.get('rework_of') and target.name not in seen:
        seen.add(target.name)
        previous = get_doc('FP Task Response', target.rework_of)
        if previous.task != target.task or previous.agent != target.agent or previous.qa_status != 'Failed':
            return False
        if previous.name == origin:
            return True
        target = previous
    return False

