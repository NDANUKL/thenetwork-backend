"""Install the version-controlled Field Operations dashboard without changing roles."""
from pathlib import Path
import frappe


def sync_dashboard():
    workspace = frappe.get_doc("Workspace", "Field Operations")
    name = "DD Field Operations Dashboard"
    block = (frappe.get_doc("Custom HTML Block", name)
             if frappe.db.exists("Custom HTML Block", name)
             else frappe.get_doc({"doctype": "Custom HTML Block", "name": name}))
    assets = Path(__file__).parent / "dashboard"
    block.private = 0
    block.html = (assets / "operations.html").read_text(encoding="utf-8")
    block.style = (assets / "operations.css").read_text(encoding="utf-8")
    block.script = (assets / "operations.js").read_text(encoding="utf-8")
    block.set("roles", [{"role": row.role} for row in workspace.roles])
    block.save(ignore_permissions=True)
