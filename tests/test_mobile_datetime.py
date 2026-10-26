from datetime import datetime
import unittest
from fieldpulse.mobile_datetime import mobile_datetime, site_datetime_iso


class MobileDatetimeTests(unittest.TestCase):
    def test_utc_and_offset_represent_same_site_time(self):
        expected = datetime(2026, 10, 23, 18, 9, 17, 641000)
        for value in ('2026-10-23T15:09:17.641Z', '2026-10-23T18:09:17.641+03:00'):
            self.assertEqual(mobile_datetime(value, 'Africa/Nairobi'), expected)

    def test_existing_database_datetime_and_empty_values(self):
        value = datetime(2026, 10, 23, 18, 9, 17)
        self.assertEqual(mobile_datetime(value), value)
        self.assertEqual(mobile_datetime('2026-10-23 18:09:17'), value)
        self.assertIsNone(mobile_datetime(None))
        self.assertIsNone(mobile_datetime(''))

    def test_invalid_timestamp_rejected(self):
        for value in ('invalid', '2026-13-23T15:00:00Z', 123):
            with self.assertRaisesRegex(ValueError, 'Invalid mobile timestamp'):
                mobile_datetime(value, 'Africa/Nairobi')

    def test_outbound_timestamp_labels_site_timezone(self):
        self.assertEqual(site_datetime_iso('2026-10-26 09:30:00', 'Africa/Nairobi'), '2026-10-26T09:30:00+03:00')
        self.assertEqual(site_datetime_iso('2026-10-26T06:30:00Z', 'Africa/Nairobi'), '2026-10-26T09:30:00+03:00')
        self.assertIsNone(site_datetime_iso(None, 'Africa/Nairobi'))
        self.assertEqual(site_datetime_iso('2026-07-26 09:30:00', 'America/New_York'), '2026-07-26T09:30:00-04:00')
        self.assertEqual(site_datetime_iso('2026-01-26 09:30:00', 'America/New_York'), '2026-01-26T09:30:00-05:00')
        with self.assertRaisesRegex(ValueError, 'Invalid site timestamp'):
            site_datetime_iso('bad', 'Africa/Nairobi')
