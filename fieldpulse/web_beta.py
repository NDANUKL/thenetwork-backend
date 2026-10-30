"""HTTP headers required by the browser SQLite WebAssembly worker."""
import frappe

def add_sqlite_web_headers(response):
    request = getattr(frappe.local, "request", None)
    path = getattr(request, "path", "") if request else ""
    if path == "/groundscouts" or path.startswith("/groundscouts/"):
        response.headers["Cross-Origin-Embedder-Policy"] = "credentialless"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    return response
