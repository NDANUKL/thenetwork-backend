"""Ownership checks keep newly deployed handlers dormant while site scripts own production."""
from functools import wraps
import json
from pathlib import Path
import frappe


def registry():
    return json.loads((Path(__file__).parent / "configuration/native-ownership.json").read_text(encoding="utf-8"))


def native_enabled(*names):
    if not frappe.conf.get("dd_native_handover_approved"):
        return False
    return not any(frappe.db.exists("Server Script", {"name": name, "disabled": 0}) for name in names)


def owned_event(*names):
    def decorate(function):
        @wraps(function)
        def run(*args, **kwargs):
            if native_enabled(*names):
                return function(*args, **kwargs)
        return run
    return decorate


def owned_api(name):
    """Hook overrides run before Server Script lookup in Frappe's handler.

    Continue through Frappe's original script executor until approved handover;
    this preserves its authentication, response shape and rate limiting.
    """
    def decorate(function):
        @wraps(function)
        def run(*args, **kwargs):
            if frappe.db.exists("Server Script", {"name": name, "disabled": 0}):
                result = frappe.get_doc("Server Script", name).execute_method()
                return result if result else frappe.response.pop("message", None)
            if not native_enabled(name):
                frappe.throw("Native backend handover has not been approved", frappe.PermissionError)
            spec = registry()["server_scripts"][name]
            if spec.get("enable_rate_limit"):
                from frappe.rate_limiter import rate_limit
                return rate_limit(limit=spec["rate_limit_count"], seconds=spec["rate_limit_seconds"])(function)(*args, **kwargs)
            return function(*args, **kwargs)
        return run
    return decorate


def extend_bootinfo(bootinfo):
    names = list(registry()["server_scripts"])
    bootinfo.dd_native_handover_active = bool(
        frappe.conf.get("dd_native_handover_approved")
        and not frappe.db.exists("Server Script", {"name": ["in", names], "disabled": 0})
    )
