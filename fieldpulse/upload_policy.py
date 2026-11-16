"""New media reservations are bounded; stored historical evidence is untouched."""
MAX_MEDIA_BYTES = 100_000_000
MAX_TASK_BYTES = 1_000_000_000


def upload_size(value):
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError('File size must be a positive whole number')
    text = str(value)
    if not text.isascii() or not text.isdigit() or len(text) > 16 or int(text) < 1:
        raise ValueError('File size must be a positive whole number')
    return int(text)


def validate_reservation(size, reserved_bytes=0):
    if size > MAX_MEDIA_BYTES:
        raise ValueError('Evidence files must be 100 MB or smaller')
    if reserved_bytes + size > MAX_TASK_BYTES:
        raise ValueError('This task has reached its 1 GB evidence upload allowance; contact the coordinator')
