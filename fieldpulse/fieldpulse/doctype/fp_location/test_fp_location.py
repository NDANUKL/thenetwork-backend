import frappe
from frappe.tests.utils import FrappeTestCase


class TestFPLocation(FrappeTestCase):
    def test_latitude_validation(self):
        # Test case that should fail (latitude too high)
        with self.assertRaises(frappe.ValidationError):
            frappe.get_doc({
                "doctype": "FP Location",
                "location_code": "TEST-LAT-HIGH",
                "location_name": "Test",
                "latitude": 90.1,
                "longitude": 0,
            }).insert()

        # Test case that should fail (latitude too low)
        with self.assertRaises(frappe.ValidationError):
            frappe.get_doc({
                "doctype": "FP Location",
                "location_code": "TEST-LAT-LOW",
                "location_name": "Test",
                "latitude": -90.1,
                "longitude": 0,
            }).insert()

    def test_longitude_validation(self):
        # Similar tests for longitude...
        # Test case that should fail (longitude too high)
        with self.assertRaises(frappe.ValidationError):
            frappe.get_doc({
                "doctype": "FP Location",
                "location_code": "TEST-LON-HIGH",
                "location_name": "Test",
                "latitude": 0,
                "longitude": 180.1,
            }).insert()

        # Test case that should fail (longitude too low)
        with self.assertRaises(frappe.ValidationError):
            frappe.get_doc({
                "doctype": "FP Location",
                "location_code": "TEST-LON-LOW",
                "location_name": "Test",
                "latitude": 0,
                "longitude": -180.1,
            }).insert()