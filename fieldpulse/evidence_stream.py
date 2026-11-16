"""Bounded ZIP output. No Frappe/database context is used during iteration."""
from collections import deque
from zipfile import ZipFile, ZIP_STORED

CHUNK_BYTES = 256 * 1024
MAX_FILE_BYTES = 100_000_000
MAX_BUNDLE_BYTES = 500_000_000
MAX_BUNDLE_FILES = 1000


class _Output:
    def __init__(self):
        self.position = 0
        self.chunks = deque()

    def tell(self):
        return self.position

    def write(self, data):
        self.position += len(data)
        if data:
            self.chunks.append(data)
        return len(data)

    def flush(self):
        pass

    def drain(self):
        while self.chunks:
            yield self.chunks.popleft()


def validate_manifest(entries):
    if len(entries) > MAX_BUNDLE_FILES:
        raise ValueError('Evidence download contains too many files')
    total = 0
    for entry in entries:
        size = entry['size']
        if type(size) is not int or size < 1 or size > MAX_FILE_BYTES:
            raise ValueError('Evidence file exceeds the 100 MB download limit or has an invalid size')
        total += size
    if total > MAX_BUNDLE_BYTES:
        raise ValueError('Evidence download exceeds 500 MB; ask the coordinator to reduce the selected evidence')


def stream_zip(entries, open_object):
    """Only emit a complete ZIP when every object's stored identity/size matches."""
    output = _Output()
    with ZipFile(output, 'w', compression=ZIP_STORED) as archive:
        for entry in entries:
            # Emit the ZIP header before waiting for object storage. Never buffer
            # more than one object chunk; the WSGI consumer supplies backpressure.
            with archive.open(entry['filename'], 'w', force_zip64=True) as target:
                yield from output.drain()
                stored = open_object(entry)
                body = stored['Body']
                try:
                    etag = str(stored.get('ETag') or '').strip().strip('"')
                    if etag != entry['etag'] or stored.get('ContentLength') != entry['size']:
                        raise ValueError('Evidence changed after verification')
                    received = 0
                    while received < entry['size']:
                        chunk = body.read(min(CHUNK_BYTES, entry['size'] - received))
                        if not chunk:
                            raise ValueError('Evidence object is truncated')
                        received += len(chunk)
                        if received > entry['size']:
                            raise ValueError('Evidence object exceeds its verified size')
                        target.write(chunk)
                        yield from output.drain()
                    if body.read(1):
                        raise ValueError('Evidence object exceeds its verified size')
                finally:
                    body.close()
            yield from output.drain()
    # Exceptions/cancellation never emit an end-of-central-directory record.
    yield from output.drain()
