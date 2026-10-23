"""Number existing tasks without renaming records or changing links."""
import frappe


def execute():
    from fieldpulse.task_numbers import next_task_number
    for task in frappe.get_all("Field Task", fields=["name", "creation", "task_number"], order_by="creation asc, name asc"):
        if not task.task_number:
            frappe.db.set_value("Field Task", task.name, "task_number", next_task_number(task.creation), update_modified=False)
