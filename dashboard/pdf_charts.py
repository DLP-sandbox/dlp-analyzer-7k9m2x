"""
dashboard/pdf_charts.py — Imágenes del Informe DLP (logo del CTA).

Las gráficas ya NO se rasterizan: se dibujan en vector (dashboard/pdf_vector.py).
Aquí solo queda el logo, con dos caminos: procesado con halo si hay PIL, y el
archivo tal cual si no. Cero llamadas a Anthropic, cero binarios externos.
"""
import io
from pathlib import Path
from typing import Optional

from PIL import Image as PILImage
from reportlab.lib.utils import ImageReader


ASSETS_DIR = Path(__file__).parent.parent / "assets"


def _autodetect_logo() -> Optional[Path]:
    """Cualquier imagen en assets/ (prioridad: nombre con 'logo', luego 'dlp')."""
    if not ASSETS_DIR.exists():
        return None
    exts = {".png", ".jpg", ".jpeg", ".webp"}
    images = [p for p in ASSETS_DIR.iterdir() if p.is_file() and p.suffix.lower() in exts]
    if not images:
        return None
    return sorted(images, key=lambda p: (0 if "logo" in p.name.lower() else 1,
                                         0 if "dlp" in p.name.lower() else 1,
                                         p.name.lower()))[0]


LOGO_PATH = _autodetect_logo()


# ── Logo con esquinas redondeadas + halo ─────────────────────────────────
def _styled_logo_png(logo_path: Path, max_dim_px: int = 900,
                     corner_radius_pct: float = 0.10,
                     glow_color=(255, 184, 77), glow_blur: int = 24,
                     glow_intensity: float = 0.65, pad_px: int = 60) -> Optional[ImageReader]:
    try:
        from PIL import ImageDraw, ImageFilter
        img = PILImage.open(str(logo_path)).convert("RGBA")
        ow, oh = img.size
        if ow >= oh:
            tw, th = max_dim_px, int(oh * max_dim_px / ow)
        else:
            th, tw = max_dim_px, int(ow * max_dim_px / oh)
        img = img.resize((tw, th), PILImage.LANCZOS)
        mask = PILImage.new("L", (tw, th), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, tw, th),
                                               radius=int(min(tw, th) * corner_radius_pct), fill=255)
        img.putalpha(mask)
        cw, ch = tw + 2 * pad_px, th + 2 * pad_px
        out = PILImage.new("RGBA", (cw, ch), (0, 0, 0, 0))
        glow = PILImage.new("RGBA", (tw, th), glow_color + (int(255 * glow_intensity),))
        glow.putalpha(mask)
        layer = PILImage.new("RGBA", (cw, ch), (0, 0, 0, 0))
        layer.paste(glow, (pad_px, pad_px), glow)
        out = PILImage.alpha_composite(out, layer.filter(ImageFilter.GaussianBlur(glow_blur)))
        shadow = PILImage.new("RGBA", (tw, th), (0, 0, 0, 130))
        shadow.putalpha(mask)
        layer = PILImage.new("RGBA", (cw, ch), (0, 0, 0, 0))
        layer.paste(shadow, (pad_px + 5, pad_px + 7), shadow)
        out = PILImage.alpha_composite(out, layer.filter(ImageFilter.GaussianBlur(8)))
        out.paste(img, (pad_px, pad_px), img)
        buf = io.BytesIO()
        out.save(buf, format="PNG")
        buf.seek(0)
        return ImageReader(buf)
    except Exception:
        return None


def _logo_directo(logo_path) -> Optional[ImageReader]:
    """Logo sin procesar: respaldo si PIL no está disponible o el halo falla.
    ReportLab incrusta el JPEG/PNG directamente, así que el CTA nunca se queda
    sin logo."""
    try:
        return ImageReader(str(logo_path))
    except Exception:
        return None
