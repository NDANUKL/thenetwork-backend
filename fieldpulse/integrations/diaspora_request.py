"""Create an operational Field Request for a Diaspora Request."""

import frappe


def create_field_request(doc, method=None):
    """Create one linked Field Request without changing the source document.

    This handler is deliberately fail-safe: an operational-request failure must
    not interrupt the Diaspora Request transaction.
    """
    try:
        if frappe.db.exists("Field Request", {"source_reference": doc.name}):
            return

        frappe.get_doc(
            {
                "doctype": "Field Request",
                "source": "Diaspora Desk",
                "source_reference": doc.name,
                "diaspora_request": doc.name,
                "field_brief": doc.summary or doc.original_brief,
                "deadline": doc.deadline_date,
                "status": "Awaiting Assignment",
            }
        ).insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(
            title=f"Field Request creation failed for Diaspora Request {doc.name}",
            message=frappe.get_traceback(),
        )
