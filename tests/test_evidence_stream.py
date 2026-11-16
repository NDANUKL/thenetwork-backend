import io
import tracemalloc
import unittest
from unittest.mock import Mock
from zipfile import ZipFile, BadZipFile
from fieldpulse.evidence_stream import stream_zip, validate_manifest, CHUNK_BYTES


def entry(size=3, filename='Photos/photo-001.jpg'):
    return dict(size=size, filename=filename, key='private-key', etag='verified')


class StreamTests(unittest.TestCase):
    def test_valid_archive_contains_exact_media_and_closes_storage_body(self):
        body = io.BytesIO(b'jpg')
        opened = Mock(return_value=dict(Body=body, ETag='"verified"', ContentLength=3))
        chunks = stream_zip([entry()], opened)
        first = next(chunks)
        self.assertTrue(first.startswith(b'PK'))
        opened.assert_not_called()
        data = first + b''.join(chunks)
        self.assertTrue(body.closed)
        with ZipFile(io.BytesIO(data)) as archive:
            self.assertEqual(archive.namelist(), ['Photos/photo-001.jpg'])
            self.assertEqual(archive.read(archive.namelist()[0]), b'jpg')

    def test_large_archive_has_bounded_peak_memory(self):
        class Body:
            remaining = 80_000_000
            closed = False
            def read(self, count):
                size = min(count, self.remaining)
                self.remaining -= size
                return b'x' * size
            def close(self): self.closed = True
        body = Body()
        tracemalloc.start()
        try:
            total = 0
            for chunk in stream_zip([entry(80_000_000)], lambda _: dict(Body=body, ETag='verified', ContentLength=80_000_000)):
                total += len(chunk)
            _, peak = tracemalloc.get_traced_memory()
        finally:
            tracemalloc.stop()
        self.assertGreater(total, 80_000_000)
        self.assertLess(peak, 4 * CHUNK_BYTES)
        self.assertTrue(body.closed)

    def test_corrupt_or_changed_objects_never_emit_a_complete_archive(self):
        for data, etag, length in [(b'jp', 'verified', 3), (b'jpg!', 'verified', 3), (b'jpg', 'changed', 3), (b'jpg', 'verified', 4)]:
            with self.subTest(data=data, etag=etag, length=length):
                body = io.BytesIO(data)
                received = []
                with self.assertRaises(ValueError):
                    for chunk in stream_zip([entry()], lambda _: dict(Body=body, ETag=etag, ContentLength=length)):
                        received.append(chunk)
                self.assertTrue(body.closed)
                with self.assertRaises(BadZipFile):
                    ZipFile(io.BytesIO(b''.join(received)))

    def test_client_cancellation_closes_the_active_object(self):
        body = io.BytesIO(b'x' * (CHUNK_BYTES + 1))
        chunks = stream_zip([entry(CHUNK_BYTES + 1)], lambda _: dict(Body=body, ETag='verified', ContentLength=CHUNK_BYTES + 1))
        next(chunks)
        next(chunks)
        chunks.close()
        self.assertTrue(body.closed)

    def test_limits_are_checked_before_opening_objects(self):
        for entries in [[entry(100_000_001)], [entry(100_000_000)] * 6, [entry()] * 1001, [entry(0)]]:
            with self.subTest(entries=len(entries)), self.assertRaises(ValueError):
                validate_manifest(entries)

    def test_empty_archive_is_valid_without_storage(self):
        with ZipFile(io.BytesIO(b''.join(stream_zip([], None)))) as archive:
            self.assertEqual(archive.namelist(), [])
