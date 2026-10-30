"""HTTP headers required by the browser SQLite WebAssembly worker."""
from pathlib import Path

import frappe


@frappe.whitelist(allow_guest=True, methods=["GET"])
def sqlite_wasm():
    """Serve Expo SQLite's public WASM through Frappe with its required MIME type."""
    wasm_directory = (
        Path(__file__).resolve().parent
        / "public"
        / "groundscouts"
        / "assets"
        / "node_modules"
        / "expo-sqlite"
        / "web"
        / "wa-sqlite"
    )
    wasm_files = sorted(wasm_directory.glob("wa-sqlite.*.wasm"))
    if len(wasm_files) != 1:
        frappe.throw("Ground Scouts SQLite WebAssembly asset is unavailable.")

    frappe.local.response.update(
        {
            "type": "download",
            "filename": "wa-sqlite.wasm",
            "filecontent": wasm_files[0].read_bytes(),
            "content_type": "application/wasm",
            "display_content_as": "inline",
        }
    )

def add_sqlite_web_headers(response):
    request = getattr(frappe.local, "request", None)
    path = getattr(request, "path", "") if request else ""
    if path == "/groundscouts" or path.startswith("/groundscouts/"):
        response.headers["Cross-Origin-Embedder-Policy"] = "credentialless"
        response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    return response
