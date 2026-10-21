"""Self-contained quotation artwork for authenticated PDF downloads."""
import base64
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
        "regular": data_uri("fonts/quotation/Carlito-Regular.ttf", "font/ttf"),
        "bold": data_uri("fonts/quotation/Carlito-Bold.ttf", "font/ttf"),
    }
