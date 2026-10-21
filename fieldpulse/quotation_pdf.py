"""Self-contained quotation artwork for authenticated PDF downloads."""
import base64
import os
import subprocess
import sys
import tempfile
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def quotation_assets():
    public = Path(__file__).resolve().parent / "public"

    def data_uri(relative_path, mime):
        encoded = base64.b64encode((public / relative_path).read_bytes()).decode("ascii")
        return f"data:{mime};base64,{encoded}"

    return {
        "logo": data_uri("images/DD_logo.png", "image/png"),
        "regular_woff": data_uri("fonts/quotation/Carlito-Regular.woff", "application/font-woff"),
        "bold_woff": data_uri("fonts/quotation/Carlito-Bold.woff", "application/font-woff"),
        "regular": data_uri("fonts/quotation/Carlito-Regular.ttf", "font/ttf"),
        "bold": data_uri("fonts/quotation/Carlito-Bold.ttf", "font/ttf"),
    }


@lru_cache(maxsize=1)
def ensure_quotation_fonts():
    """Make Carlito available to Linux Qt/Fontconfig, not just CSS @font-face.

    Use only the worker user's font directory. No sudo, system font changes,
    remote downloads, or environment changes during concurrent requests.
    """
    if not sys.platform.startswith("linux"):
        return
    source = Path(__file__).resolve().parent / "public/fonts/quotation"
    data_root = Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local/share")
    if not data_root.is_absolute():
        data_root = Path.home() / ".local/share"
    font_dir = data_root / "fonts/fieldpulse-quotation"
    font_dir.mkdir(parents=True, exist_ok=True)
    changed = False
    try:
        for weight in ("Regular", "Bold"):
            filename = f"Carlito-{weight}.ttf"
            target = font_dir / filename
            content = (source / filename).read_bytes()
            if target.exists() and target.read_bytes() == content:
                continue
            with tempfile.NamedTemporaryFile(dir=font_dir, prefix=".carlito-", delete=False) as temporary:
                temporary.write(content)
                temporary_path = Path(temporary.name)
            try:
                temporary_path.replace(target)
            finally:
                temporary_path.unlink(missing_ok=True)
            changed = True
        if changed:
            subprocess.run(["fc-cache", "-f", str(font_dir)], check=True, capture_output=True, timeout=30)
        for weight in ("Regular", "Bold"):
            match = subprocess.run(
                ["fc-match", "-f", "%{file}", f"Carlito:style={weight}"],
                check=True, capture_output=True, text=True, timeout=10,
            )
            resolved = Path(match.stdout.strip()).resolve()
            if resolved != (font_dir / f"Carlito-{weight}.ttf").resolve():
                raise RuntimeError(f"PDF renderer substituted Carlito {weight}")
    except (OSError, subprocess.SubprocessError) as error:
        raise RuntimeError("Carlito fonts could not be registered for quotation PDFs") from error
