"""Human-readable task references; document IDs remain unchanged."""
from frappe.model.naming import make_autoname
from frappe.utils import getdate


def next_task_number(created=None):
    year = getdate(created).year
    return make_autoname(f"TK-{year}-.#####")
