"""Shared Diaspora Desk email presentation helpers."""
import json
import re
from html import escape
from pathlib import Path


DISPLAY_NAME = "Diaspora Desk"


def sender_address(address):
    """Add the brand label at the provider boundary, keeping settings plain."""
    address = str(address or "").strip()
    # Frappe may HTML-escape angle brackets in a setting saved as a mailbox
    # phrase. Normalize only known escaped delimiters, then avoid nesting a name.
    address = address.replace("&lt;", "<").replace("&gt;", ">")
    if "<" in address and address.endswith(">"):
        address = address[address.rfind("<") + 1:-1].strip()
    return f"{DISPLAY_NAME} <{address}>" if address else ""


def render_email(*, title, body, origin, eyebrow="DIASPORA DESK", link="", label="", note="", preheader=None,
                 body_is_html=False):
    """Render content in the branded email shell, escaping body text by default."""
    origin = (origin or "https://diaspora-desk.com").rstrip("/")
    values = {
        "origin": origin,
        "title": title,
        "eyebrow": eyebrow,
        "preheader": preheader or title,
        "body": body,
        "link": link or "",
        "label": label or "",
        "note": note or "",
    }
    shell = json.loads((Path(__file__).parent / "templates/emails/dd_shell.json").read_text(encoding="utf-8"))
    rendered = re.sub(r"{{(\w+)}}", lambda match: (
        str(values[match[1]]) if body_is_html and match[1] == "body"
        else escape(str(values[match[1]]), quote=True)
    ), shell)
    if not label or not link:
        rendered = re.sub(r'<table role="presentation" align="center" cellpadding="0" cellspacing="0" style="margin:0 auto">.*?</table>', "", rendered, count=1)
    if not note:
        rendered = re.sub(r'<p style="margin:24px 0 0;font-size:13px;line-height:1.7;color:#607383">.*?</p>', "", rendered, count=1)
    return rendered
