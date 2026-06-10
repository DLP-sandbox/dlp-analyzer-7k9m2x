"""
dashboard/pdf_report.py — Generador de PDF lead-magnet para StockAnalysis.

Genera 3 páginas landscape 16:9 (1920×1080 pt) con:
  · Página 1: Síntesis ejecutiva (hero + snowflake + tesis + KPIs)
  · Página 2: Análisis por dimensiones (8 agentes + 6 mini-cards detalladas)
  · Página 3: Veredicto + CTA Club DLP con logo y QR

Garantía: CERO llamadas a Anthropic. Esta función NO importa anthropic, NO
instancia Orchestrator, NO toca client.messages. Solo lee el StockAnalysis
ya construido y renderiza. Verificable con:
    grep -nE "anthropic|client\\.messages|Orchestrator" dashboard/pdf_report.py
"""
import io
from pathlib import Path
from typing import Optional

from PIL import Image as PILImage
import qrcode

from reportlab.lib.colors import Color, HexColor
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas


# ── Geometría ───────────────────────────────────────────────────────────
PAGE_W = 1920.0
PAGE_H = 1080.0
MARGIN_X = 70.0
MARGIN_Y = 60.0

# ── Paleta (espejo de dashboard/styles.py) ──────────────────────────────
BG_DEEP    = HexColor("#080B0F")
BG_CARD    = HexColor("#141920")
BG_CARD2   = HexColor("#1A2030")
BG_CTA     = HexColor("#0F1419")
ORANGE     = HexColor("#FFB84D")
ORANGE_DK  = HexColor("#FFA500")
GOLD       = HexColor("#FFD740")
GREEN      = HexColor("#00FF88")
GREEN_DK   = HexColor("#00C853")
RED        = HexColor("#FF3B5C")
RED_DK     = HexColor("#E53935")
BLUE       = HexColor("#4A9EFF")
BLUE_DK    = HexColor("#2196F3")
TEXT_HI    = HexColor("#FFFFFF")
TEXT_MD    = HexColor("#E4E7EC")
TEXT_LO    = HexColor("#7A8898")
TEXT_DIM   = HexColor("#5A6878")
BORDER     = HexColor("#1E2530")

# ── Paths ───────────────────────────────────────────────────────────────
ASSETS_DIR = Path(__file__).parent.parent / "assets"
FONTS_DIR  = ASSETS_DIR / "fonts"


def _autodetect_logo() -> Optional[Path]:
    """Auto-detecta cualquier imagen en assets/ (excluyendo README y subdirs).
    Acepta nombres random tipo 'WhatsApp Image 2026-06-09.jpeg'.
    Prioridad: club*logo*, *logo*, *dlp*, primero por nombre alfabético."""
    if not ASSETS_DIR.exists():
        return None
    exts = {".png", ".jpg", ".jpeg", ".webp"}
    images = [p for p in ASSETS_DIR.iterdir()
              if p.is_file() and p.suffix.lower() in exts]
    if not images:
        return None
    # Prioridad: archivos con "logo" o "dlp" en el nombre
    by_priority = sorted(images, key=lambda p: (
        0 if "logo" in p.name.lower() else 1,
        0 if "dlp" in p.name.lower() else 1,
        p.name.lower(),
    ))
    return by_priority[0]


LOGO_PATH = _autodetect_logo()

# ── CTA ─────────────────────────────────────────────────────────────────
CLUB_DLP_URL    = "https://diariolargoplazo.com"
CLUB_DLP_HANDLE = "@diariolargoplazo"


# ── Registro de fuentes TTF (espejo de diariolargoplazo.com) ────────────
# Tipografía oficial de la web:
#   - Headings: Bricolage Grotesque (400/700/800)
#   - Body:     Inter (400/700)
# Fallback a Helvetica si no están en assets/fonts/.

def _try_register_fonts() -> tuple[str, str, str, str, str]:
    """Registra Helvetica Neue desde la .ttc de macOS (preferido), con
    fallback a las TTFs en assets/fonts/, y finalmente a built-in Helvetica.
    Returns: (body_reg, body_bold, mono_reg, display_bold, display_xbold)
    """
    # 1) Intento Helvetica Neue desde el sistema macOS (.ttc multi-face)
    sys_ttc = Path("/System/Library/Fonts/HelveticaNeue.ttc")
    if sys_ttc.exists():
        # Mapeo: faceIndex → nombre que usaremos en reportlab
        ttc_faces = [
            (0,  "HelveticaNeue"),         # Regular
            (1,  "HelveticaNeue-Bold"),    # Bold
            (10, "HelveticaNeue-Medium"),  # Medium (para "mono" semántico)
        ]
        for idx, name in ttc_faces:
            try:
                pdfmetrics.registerFont(TTFont(name, str(sys_ttc), subfontIndex=idx))
            except Exception:
                pass

    # 2) Fallback / extras desde assets/fonts/
    candidates = [
        ("Inter",                     "Inter-Regular.ttf"),
        ("Inter-Bold",                "Inter-Bold.ttf"),
        ("BricolageGrotesque",        "BricolageGrotesque-Regular.ttf"),
        ("BricolageGrotesque-Bold",   "BricolageGrotesque-Bold.ttf"),
        ("BricolageGrotesque-XBold",  "BricolageGrotesque-ExtraBold.ttf"),
    ]
    for name, fname in candidates:
        path = FONTS_DIR / fname
        if path.exists():
            try:
                pdfmetrics.registerFont(TTFont(name, str(path)))
            except Exception:
                pass

    available = set(pdfmetrics.getRegisteredFontNames())
    # Prioridad: Helvetica Neue → Inter → built-in Helvetica
    if "HelveticaNeue" in available:
        body_reg  = "HelveticaNeue"
        body_bold = "HelveticaNeue-Bold"
        mono      = "HelveticaNeue-Medium" if "HelveticaNeue-Medium" in available else body_bold
        display_b = "HelveticaNeue-Bold"
        # Para "display XL" — usamos Bold (no hay XBold en la familia Neue)
        display_xb = "HelveticaNeue-Bold"
    elif "Inter" in available:
        body_reg   = "Inter"
        body_bold  = "Inter-Bold"
        mono       = body_bold
        display_b  = "BricolageGrotesque-Bold"  if "BricolageGrotesque-Bold" in available else body_bold
        display_xb = "BricolageGrotesque-XBold" if "BricolageGrotesque-XBold" in available else display_b
    else:
        body_reg = "Helvetica"
        body_bold = "Helvetica-Bold"
        mono = body_bold
        display_b = body_bold
        display_xb = body_bold
    return body_reg, body_bold, mono, display_b, display_xb


FONT_REG, FONT_BOLD, FONT_MONO, FONT_DISPLAY, FONT_DISPLAY_XL = _try_register_fonts()
# Alias por compatibilidad con código previo (FONT_MONO_BOLD = display bold ahora)
FONT_MONO_BOLD = FONT_DISPLAY


# ── Helpers de coordenadas (top-down) ──────────────────────────────────
def _y(top: float) -> float:
    """Convierte offset desde el TOP de la página a coordenada y de reportlab."""
    return PAGE_H - top


# ── Helpers de dibujo ───────────────────────────────────────────────────
def _fill_bg(c, color=BG_DEEP):
    c.setFillColor(color)
    c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)


def _box(c, x, top, w, h, *, r=10, fill=None, stroke=None, stroke_w=1):
    """Dibuja un rounded rect usando coordenadas top-down (top = offset desde el techo)."""
    if fill is not None:
        c.setFillColor(fill)
    if stroke is not None:
        c.setStrokeColor(stroke)
        c.setLineWidth(stroke_w)
    c.roundRect(
        x, _y(top + h), w, h, r,
        stroke=(1 if stroke is not None else 0),
        fill=(1 if fill is not None else 0),
    )


def _text(c, txt, x, top, *, font=None, size=12, color=TEXT_MD, anchor="left"):
    """Escribe texto en coords top-down. `top` = offset desde el techo a la BASELINE."""
    if font is None:
        font = FONT_REG
    c.setFont(font, size)
    c.setFillColor(color)
    s = str(txt) if txt is not None else "—"
    y = _y(top)
    if anchor == "center":
        c.drawCentredString(x, y, s)
    elif anchor == "right":
        c.drawRightString(x, y, s)
    else:
        c.drawString(x, y, s)


def _wrap(c, txt, x, top, width, *, font=None, size=12, color=TEXT_MD,
          line_height=1.45, max_lines=None) -> float:
    """Wrap-text simple por palabra. Devuelve la siguiente y top-down libre."""
    if font is None:
        font = FONT_REG
    if not txt:
        return top
    c.setFont(font, size)
    c.setFillColor(color)
    words = str(txt).split()
    lines, line = [], ""
    for w in words:
        test = (line + " " + w).strip()
        if c.stringWidth(test, font, size) > width and line:
            lines.append(line)
            line = w
        else:
            line = test
    if line:
        lines.append(line)
    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]
        last = lines[-1]
        ell = "…"
        while c.stringWidth(last + ell, font, size) > width and last:
            last = last[:-1]
        lines[-1] = last.rstrip() + ell

    lh = size * line_height
    cy = top
    for ln in lines:
        c.drawString(x, _y(cy), ln)
        cy += lh
    return cy


def _score_color(score) -> Color:
    if score is None:
        return TEXT_LO
    try:
        s = float(score)
    except Exception:
        return TEXT_LO
    if s >= 70: return GREEN
    if s >= 50: return ORANGE
    return RED


def _rec_palette(rec: str) -> tuple[Color, Color]:
    """(fill_color, text_color) para el badge de recomendación."""
    r = (rec or "").upper()
    if r in ("MUY ATRACTIVO", "STRONG BUY"):
        return GREEN, HexColor("#001A06")
    if r in ("ATRACTIVO", "BUY"):
        return BLUE, TEXT_HI
    if r in ("EVITAR", "PASS"):
        return RED, TEXT_HI
    return ORANGE, HexColor("#1A0F00")  # WATCH default


def _safe(val, default="—"):
    if val is None or val == "":
        return default
    return str(val)


def _extract_insight(report, max_chars: int = 260) -> str:
    """Extrae el insight clave del campo `analysis` de un AgentReport.

    Reglas:
    - Toma las PRIMERAS 1-2 oraciones (la síntesis del agente DLP siempre
      arranca con la conclusión).
    - Si 2 oraciones caben en max_chars → devuelve ambas.
    - Si solo 1 cabe → devuelve esa.
    - Si ni 1 cabe → trunca por palabra con ellipsis.
    - Limpia saltos de línea, dobles espacios, citas inválidas.
    - Devuelve "" si no hay analysis (caller decide qué mostrar).
    """
    if report is None:
        return ""
    text = getattr(report, "analysis", "") or ""
    if not text:
        return ""

    import re as _re
    # Normalizar whitespace: \n\n → ". ", \n → " ", colapsar espacios
    cleaned = _re.sub(r"\n+", " ", text)
    cleaned = _re.sub(r"\s+", " ", cleaned).strip()
    if not cleaned:
        return ""

    # Split por sentence boundary (. ! ?) seguido de espacio + mayúscula/digit
    # Acepta también ". " sin lookahead estricto, regex simple por palabra.
    sentences = _re.split(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÑ¿¡«\"0-9])", cleaned)
    sentences = [s.strip() for s in sentences if s.strip()]
    if not sentences:
        return cleaned[:max_chars].rstrip() + "…"

    # Probar 2 oraciones
    if len(sentences) >= 2:
        two = (sentences[0] + " " + sentences[1]).strip()
        if len(two) <= max_chars:
            return two

    # Solo 1ra oración
    first = sentences[0]
    if len(first) <= max_chars:
        return first

    # Hard-truncate por palabra
    words = first.split()
    out = ""
    for w in words:
        candidate = (out + " " + w).strip()
        if len(candidate) + 1 > max_chars:
            break
        out = candidate
    return (out.rstrip(",;: ") + "…") if out else first[:max_chars - 1] + "…"


def _truncate_by_sentence(text: str, max_chars: int = 700) -> str:
    """Trunca un texto largo por límite de oración (no corta mitad de palabra).

    Acumula oraciones completas hasta superar `max_chars`. Si la primera
    oración ya supera max_chars, hace hard-truncate por palabra con '…'.
    Limpia saltos de línea y dobles espacios.
    """
    if not text:
        return ""
    import re as _re
    cleaned = _re.sub(r"\n+", " ", text)
    cleaned = _re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) <= max_chars:
        return cleaned

    sentences = _re.split(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÑ¿¡«\"0-9])", cleaned)
    sentences = [s.strip() for s in sentences if s.strip()]
    if not sentences:
        return cleaned[:max_chars].rstrip() + "…"

    out = ""
    for s in sentences:
        candidate = (out + " " + s).strip() if out else s
        if len(candidate) > max_chars:
            break
        out = candidate

    if not out:
        # 1ra oración ya supera max_chars → truncate por palabra
        first = sentences[0]
        words = first.split()
        out = ""
        for w in words:
            cand = (out + " " + w).strip() if out else w
            if len(cand) + 1 > max_chars:
                break
            out = cand
        return (out.rstrip(",;: ") + "…") if out else first[:max_chars - 1] + "…"

    # Si quedó truncado (hay más oraciones después), añadir ellipsis
    if len(out) < len(cleaned):
        out = out.rstrip(".!? ") + "…"
    return out


def _extract_ratio(s, default: str = "—") -> str:
    """Extrae solo el ratio numérico (ej "1.85:1") de strings tipo
    "1.16:1 a precio actual; 1.85:1 si entra a $195".
    Si hay varios, devuelve el primero (que suele ser el actual).
    Si no encuentra ratio, devuelve default.
    """
    if not s:
        return default
    import re as _re
    text = str(s)
    m = _re.search(r"\d+(?:[.,]\d+)?\s*[:\\/]\s*\d+(?:[.,]\d+)?", text)
    if not m:
        return default
    return m.group(0).replace(" ", "").replace(",", ".")


# ── Glosario: términos técnicos → lenguaje plano (cero llamadas API) ───
_TECH_TO_PLAIN = [
    # Términos financieros / valoración
    (r"\bmoat\b",                "ventaja competitiva"),
    (r"\bMoat\b",                "Ventaja competitiva"),
    (r"\bROIC\b",                "rentabilidad del capital"),
    (r"\bROE\b",                 "rentabilidad sobre patrimonio"),
    (r"\bROA\b",                 "rentabilidad sobre activos"),
    (r"\bROIC/ROE\b",            "rentabilidad del capital"),
    (r"\bEV/EBITDA\b",           "múltiplo de valoración"),
    (r"\bFCF\b",                 "flujo de caja libre"),
    (r"\bEPS\b",                 "ganancias por acción"),
    (r"\bTAM\b",                 "mercado total"),
    (r"\bbeta\b",                "sensibilidad al mercado"),
    (r"\bBeta\b",                "Sensibilidad al mercado"),
    (r"\bguidance\b",            "proyecciones de la empresa"),
    (r"\bGuidance\b",            "Proyecciones de la empresa"),
    (r"\bconsensus\b",           "consenso de analistas"),
    (r"\bmega-cap\b",            "empresa de gran tamaño"),
    (r"\bmid-cap\b",             "empresa de tamaño medio"),
    (r"\bsmall-cap\b",           "empresa pequeña"),
    (r"\bbuyback\b",             "recompra de acciones"),
    (r"\bbuybacks\b",            "recompras de acciones"),
    (r"\bearnings beat",         "superación de expectativas"),
    (r"\bbeat rate\b",           "tasa de superaciones"),
    (r"\bupgrade\b",             "mejora de recomendación"),
    (r"\bupgrades\b",            "mejoras de recomendación"),
    (r"\bdowngrade\b",           "rebaja de recomendación"),
    # Términos técnicos de mercado
    (r"\bRSI\b",                 "indicador de fuerza relativa"),
    (r"\bMACD\b",                "indicador de tendencia MACD"),
    (r"\bSMA\b",                 "media móvil"),
    (r"\bATR\b",                 "volatilidad típica"),
    (r"\bStage 1\b",             "fase de acumulación (lateral)"),
    (r"\bStage 2\b",             "fase de subida sostenida"),
    (r"\bStage 3\b",             "fase de distribución (techo)"),
    (r"\bStage 4\b",             "fase de bajada sostenida"),
    (r"\bbreakout\b",            "ruptura al alza"),
    (r"\bbreakdown\b",           "ruptura a la baja"),
    (r"\bpullback\b",            "retroceso del precio"),
    (r"\bsetup\b",               "configuración técnica"),
    (r"\binsiders?\b",           "ejecutivos internos"),
    (r"\bshort interest\b",      "apuestas a la baja"),
    (r"\bhyperscalers?\b",       "grandes empresas de nube (AWS, Google, Azure)"),
    (r"\bcustom silicon\b",      "chips propios"),
    (r"\bcrowded\b",             "muy concentrado"),
    (r"\byields a 10 años?\b",   "tasas a 10 años"),
    (r"\byields?\b",             "tasas de interés"),
    (r"\brisk-on\b",             "apetito por riesgo alto"),
    (r"\brisk-off\b",            "aversión al riesgo"),
    (r"\bbear market\b",         "mercado bajista"),
    (r"\bbull market\b",         "mercado alcista"),
    (r"\bsell-off\b",            "caída fuerte"),
    (r"\bcompounder\b",          "máquina de generar valor a largo plazo"),
    (r"\bcompounding\b",         "crecimiento compuesto"),
    (r"\bP/E forward\b",         "múltiplo P/E estimado"),
    (r"\bforward P/E\b",         "múltiplo P/E estimado"),
    (r"\btrailing P/E\b",        "múltiplo P/E histórico"),
    (r"\bP/E trailing\b",        "múltiplo P/E histórico"),
]


def _simplify_lang(text: str) -> str:
    """Reemplaza términos técnicos por lenguaje plano (sin API).
    Útil para fortalezas/debilidades en el reporte descargable."""
    if not text:
        return text
    import re as _re_simp
    out = str(text)
    for pattern, replacement in _TECH_TO_PLAIN:
        try:
            out = _re_simp.sub(pattern, replacement, out)
        except Exception:
            continue
    # Limpiar dobles espacios y parentesis vacíos
    out = _re_simp.sub(r"\s+", " ", out).strip()
    out = _re_simp.sub(r"\(\s*\)", "", out)
    return out


def _truncate_text(s: str, max_chars: int, ellipsis: str = "…") -> str:
    """Trunca un string a max_chars sin cortar palabras (siempre que pueda).
    Útil para campos del LLM que vienen con explicaciones largas."""
    if not s:
        return ""
    s = str(s).strip()
    if len(s) <= max_chars:
        return s
    # Cortar por palabra
    words = s.split()
    out = ""
    for w in words:
        cand = (out + " " + w).strip() if out else w
        if len(cand) + len(ellipsis) > max_chars:
            break
        out = cand
    if not out:
        return s[:max_chars - len(ellipsis)].rstrip() + ellipsis
    return out.rstrip(",;: ") + ellipsis


def _to_float(val, default=None):
    """Coerce a cualquier cosa → float o default. NO crashea con strings raros.
    Si recibe un string como '4.3% si entra a precio actual...', extrae el
    primer número que aparezca (incluyendo decimales con '.' o ',').
    """
    if val is None or val == "":
        return default
    if isinstance(val, (int, float)):
        try:
            f = float(val)
            return f if f == f else default  # filter NaN
        except Exception:
            return default
    # String → extraer primer número
    import re as _re
    s = str(val).replace(",", ".")
    m = _re.search(r"-?\d+(?:\.\d+)?", s)
    if not m:
        return default
    try:
        return float(m.group(0))
    except Exception:
        return default


# ── Plotly chart → PNG via kaleido ──────────────────────────────────────
def _chart_png(fig, width_px: int, height_px: int) -> Optional[ImageReader]:
    try:
        png_bytes = fig.to_image(
            format="png",
            width=width_px,
            height=height_px,
            scale=2,
            engine="kaleido",
        )
        return ImageReader(io.BytesIO(png_bytes))
    except Exception:
        return None


# ── Logo procesado: bordes redondeados + halo glow ─────────────────────
def _styled_logo_png(logo_path: Path, max_dim_px: int = 900,
                     corner_radius_pct: float = 0.10,
                     glow_color=(255, 184, 77),
                     glow_blur: int = 24,
                     glow_intensity: float = 0.65,
                     pad_px: int = 60) -> Optional[ImageReader]:
    """Devuelve el logo CONSERVANDO su aspect ratio original, con esquinas
    redondeadas + halo glow exterior + sombra. No lo recorta a cuadrado.

    Args:
      max_dim_px: dimensión máxima (alto o ancho, lo que sea mayor del logo).
      corner_radius_pct: radio de esquina como % del lado menor.
      glow_color: color RGB del halo.
      glow_blur: radio del blur gaussiano (px).
      glow_intensity: 0-1 opacidad del glow.
      pad_px: padding alrededor del logo para que el glow se vea.
    """
    try:
        from PIL import ImageDraw, ImageFilter

        # 1. Cargar logo — CONSERVAR aspect ratio
        img = PILImage.open(str(logo_path)).convert("RGBA")
        ow, oh = img.size
        # Escalar para que la dim mayor = max_dim_px
        if ow >= oh:
            target_w = max_dim_px
            target_h = int(oh * max_dim_px / ow)
        else:
            target_h = max_dim_px
            target_w = int(ow * max_dim_px / oh)
        img = img.resize((target_w, target_h), PILImage.LANCZOS)

        # 2. Máscara redondeada (mantiene la forma rectangular)
        mask = PILImage.new("L", (target_w, target_h), 0)
        draw = ImageDraw.Draw(mask)
        radius = int(min(target_w, target_h) * corner_radius_pct)
        draw.rounded_rectangle((0, 0, target_w, target_h),
                                radius=radius, fill=255)
        img.putalpha(mask)

        # 3. Canvas final con padding (para alojar el glow exterior)
        canvas_w = target_w + 2 * pad_px
        canvas_h = target_h + 2 * pad_px
        canvas_img = PILImage.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))

        # 4. Capa GLOW
        glow_solid = PILImage.new(
            "RGBA", (target_w, target_h),
            glow_color + (int(255 * glow_intensity),))
        glow_solid.putalpha(mask)
        glow_layer = PILImage.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        glow_layer.paste(glow_solid, (pad_px, pad_px), glow_solid)
        glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(glow_blur))
        canvas_img = PILImage.alpha_composite(canvas_img, glow_layer)

        # 5. Capa SOMBRA (desplazada para profundidad)
        shadow_solid = PILImage.new("RGBA", (target_w, target_h),
                                     (0, 0, 0, 130))
        shadow_solid.putalpha(mask)
        shadow_layer = PILImage.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        shadow_layer.paste(shadow_solid,
                            (pad_px + 5, pad_px + 7), shadow_solid)
        shadow_layer = shadow_layer.filter(ImageFilter.GaussianBlur(8))
        canvas_img = PILImage.alpha_composite(canvas_img, shadow_layer)

        # 6. Pegar logo encima
        canvas_img.paste(img, (pad_px, pad_px), img)

        # 7. Exportar
        buf = io.BytesIO()
        canvas_img.save(buf, format="PNG")
        buf.seek(0)
        return ImageReader(buf)
    except Exception:
        return None


# ── QR code para CTA ────────────────────────────────────────────────────
def _qr_image(url: str, size_px: int = 480) -> Optional[ImageReader]:
    try:
        qr = qrcode.QRCode(
            version=1,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=2,
        )
        qr.add_data(url)
        qr.make(fit=True)
        img = qr.make_image(fill_color="#FFB84D", back_color="#0F1419")
        pil = img.get_image() if hasattr(img, "get_image") else img
        pil = pil.convert("RGB").resize((size_px, size_px), PILImage.LANCZOS)
        buf = io.BytesIO()
        pil.save(buf, format="PNG")
        buf.seek(0)
        return ImageReader(buf)
    except Exception:
        return None


# ═════════════════════════════════════════════════════════════════════════
#                              ENTRY POINT
# ═════════════════════════════════════════════════════════════════════════

def build_analysis_pdf(analysis) -> bytes:
    """Genera el PDF de 4 páginas landscape 1920×1080 y devuelve los bytes.

    Cero llamadas a Anthropic — todos los datos vienen del StockAnalysis
    que ya fue construido por el orquestador en una llamada previa.

    Estructura:
      1. Dashboard general (gauge + radar + bars + KPIs)
      2. Fundamentales + Tendencia técnica simple
      3. Los 8 agentes con narrativa
      4. Fortalezas/Debilidades + chart precios + CTA
    """
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(PAGE_W, PAGE_H))
    c.setTitle(f"Análisis DLP — {analysis.ticker}")
    c.setAuthor("Diario Largo Plazo · DLP Market Analyzer")
    c.setSubject("Análisis de inversión a largo plazo")
    c.setCreator("DLP Market Analyzer")

    _page_1_synthesis(c, analysis)
    c.showPage()
    _page_2_finance_technical(c, analysis)
    c.showPage()
    _page_3_pillars(c, analysis)
    c.showPage()
    _page_4_finale(c, analysis)
    c.showPage()

    c.save()
    return buf.getvalue()


# ═════════════════════════════════════════════════════════════════════════
#                       PÁGINA 1 — SÍNTESIS EJECUTIVA
# ═════════════════════════════════════════════════════════════════════════
def _page_1_synthesis(c, a):
    _fill_bg(c)

    # ── HERO STRIP (compacto, sin tesis aquí) ───────────────────────────
    hero_top = MARGIN_Y
    hero_h = 240
    _box(c, MARGIN_X, hero_top, PAGE_W - 2*MARGIN_X, hero_h,
         r=14, fill=BG_CARD, stroke=ORANGE, stroke_w=1)

    # Brand top-right
    _text(c, "◈  DLP MARKET ANALYZER", PAGE_W - MARGIN_X - 28, hero_top + 26,
          font=FONT_MONO_BOLD, size=12, color=ORANGE, anchor="right")
    _text(c, _safe(a.timestamp)[:10], PAGE_W - MARGIN_X - 28, hero_top + 46,
          font=FONT_MONO, size=11, color=TEXT_LO, anchor="right")

    # Calcular ancho disponible para ticker (no debe llegar al lado derecho)
    right_zone_x = PAGE_W - MARGIN_X - 60 - 320

    # Ticker XL (left) — Bricolage ExtraBold
    tx = MARGIN_X + 44
    _text(c, a.ticker, tx, hero_top + 124, font=FONT_DISPLAY_XL, size=92, color=ORANGE)

    company = (a.company_name or a.ticker)[:50]
    _text(c, company, tx, hero_top + 175, font=FONT_BOLD, size=22, color=TEXT_HI)

    horizon = _truncate_text(_safe(a.time_horizon, "no definido"), max_chars=40)
    sub = f"{_safe(a.sector)}   ·   Horizonte: {horizon}"
    left_w = right_zone_x - tx - 30
    _wrap(c, sub, tx, hero_top + 204, width=left_w,
          font=FONT_REG, size=16, color=TEXT_LO,
          line_height=1.3, max_lines=1)

    # Brief alpha opportunity (1 oración) — sustituye al gran tesis del centro
    alpha_brief = _truncate_by_sentence(getattr(a, "alpha_opportunity", "") or "", 180)
    if alpha_brief:
        _wrap(c, alpha_brief, tx, hero_top + 230, width=left_w,
              font=FONT_REG, size=14, color=GOLD,
              line_height=1.3, max_lines=1)

    # Composite score (right side)
    sc_f = _to_float(a.composite_score)
    sc_color = _score_color(sc_f if sc_f is not None else 50)
    _text(c, f"{sc_f:.1f}" if sc_f is not None else "—",
          PAGE_W - MARGIN_X - 60, hero_top + 130,
          font=FONT_DISPLAY_XL, size=84, color=sc_color, anchor="right")
    _text(c, "COMPOSITE  /  100", PAGE_W - MARGIN_X - 60, hero_top + 168,
          font=FONT_DISPLAY, size=12, color=TEXT_LO, anchor="right")

    # Recommendation badge + conviction
    rec = a.recommendation or "EN OBSERVACIÓN"
    fill_c, text_c = _rec_palette(rec)
    badge_w, badge_h = 320, 42
    badge_x = PAGE_W - MARGIN_X - 60 - badge_w
    badge_top = hero_top + 184
    _box(c, badge_x, badge_top, badge_w, badge_h, r=8, fill=fill_c)
    _text(c, rec.upper(), badge_x + badge_w/2, badge_top + 28,
          font=FONT_BOLD, size=16, color=text_c, anchor="center")

    # Conviction siempre en español
    _CONV_ES = {"HIGH": "ALTA", "MEDIUM": "MEDIA", "LOW": "BAJA"}
    conv_raw = a.conviction_level or "MEDIUM"
    conv = _CONV_ES.get(conv_raw.upper(), conv_raw)
    conv_w = 140
    conv_x = badge_x - conv_w - 14
    _box(c, conv_x, badge_top, conv_w, badge_h, r=8,
         fill=BG_CARD2, stroke=ORANGE, stroke_w=1)
    _text(c, conv.upper(), conv_x + conv_w/2, badge_top + 22,
          font=FONT_DISPLAY, size=14, color=ORANGE, anchor="center")
    _text(c, "CONVICCIÓN", conv_x + conv_w/2, badge_top + 37,
          font=FONT_REG, size=9, color=TEXT_LO, anchor="center")

    # ── CENTRO: DASHBOARD 3-PANEL (gauge | snowflake | desglose) ────────
    # Mirroring del Overview real de la app — 3 cards visuales lado a lado.
    mid_top = hero_top + hero_h + 22
    mid_h = 500
    gap_card = 18
    panel_w = (PAGE_W - 2 * MARGIN_X - gap_card * 2) / 3  # ≈ 581pt

    # ── PANEL 1 — GAUGE (DLP SCORE) ──
    p1_x = MARGIN_X
    _box(c, p1_x, mid_top, panel_w, mid_h, r=12,
         fill=BG_CARD, stroke=BORDER, stroke_w=1)
    _text(c, "DLP SCORE", p1_x + 28, mid_top + 38,
          font=FONT_DISPLAY, size=19, color=TEXT_LO)
    _text(c, rec.upper(), p1_x + 28, mid_top + 64,
          font=FONT_DISPLAY, size=14, color=fill_c)

    try:
        from dashboard.charts import build_gauge
        g_fig = build_gauge(sc_f if sc_f is not None else 50, rec)
        g_fig.update_layout(
            paper_bgcolor="#141920", plot_bgcolor="#141920",
            margin=dict(l=60, r=60, t=40, b=40),
            font=dict(family="Helvetica Neue, Helvetica, sans-serif",
                      color="#E4E7EC", size=30),
            height=520,
        )
        try:
            g_fig.update_traces(
                title=None,
                gauge=dict(
                    axis=dict(tickfont=dict(size=26, color="#7A8898")),
                    # Glow: bar más gruesa + bordes brillantes en el threshold
                    bar=dict(thickness=0.42, color=sc_color.hexval()[2:] if hasattr(sc_color, "hexval") else "#FFB84D"),
                ),
                selector=dict(type="indicator"),
            )
        except Exception:
            pass
        # Annotation del número grande
        try:
            for ann in g_fig.layout.annotations or []:
                ann.font.size = 150
                ann.y = 0.08
        except Exception:
            pass
        g_png = _chart_png(g_fig, width_px=1200, height_px=1100)
        if g_png:
            cw = panel_w - 40
            ch = mid_h - 90
            c.drawImage(g_png, p1_x + 20, _y(mid_top + mid_h - 20),
                        width=cw, height=ch,
                        preserveAspectRatio=True, mask='auto')
    except Exception:
        # Fallback: número grande centrado
        _text(c, f"{sc_f:.0f}" if sc_f is not None else "—",
              p1_x + panel_w/2, mid_top + mid_h/2 + 30,
              font=FONT_DISPLAY_XL, size=120, color=sc_color, anchor="center")
        _text(c, "/100", p1_x + panel_w/2, mid_top + mid_h/2 + 70,
              font=FONT_DISPLAY, size=18, color=TEXT_LO, anchor="center")

    # ── PANEL 2 — SNOWFLAKE (PERFIL DE CALIDAD) ──
    p2_x = p1_x + panel_w + gap_card
    _box(c, p2_x, mid_top, panel_w, mid_h, r=12,
         fill=BG_CARD, stroke=BORDER, stroke_w=1)
    _text(c, "PERFIL DE CALIDAD", p2_x + 28, mid_top + 38,
          font=FONT_DISPLAY, size=19, color=TEXT_LO)
    _text(c, "5 DIMENSIONES · 0–20 c/u", p2_x + 28, mid_top + 64,
          font=FONT_REG, size=14, color=TEXT_DIM)

    try:
        from dashboard.charts import build_snowflake
        import plotly.graph_objects as go
        sf_fig = build_snowflake(a.snowflake or {})
        # Sobrescribir labels: cortas, sin emojis, sin <b>N</b> embebido.
        # CRECIMIENTO/MOMENTUM se acortan a 7 chars para que NO se corten
        # contra el borde del card al renderizarse con font huge.
        _short = ["VALOR", "CALIDAD", "CRECIM.", "MOMENT.", "FUTURO"]
        _short_closed = _short + [_short[0]]
        for tr in sf_fig.data:
            if hasattr(tr, "theta") and tr.theta:
                try:
                    tr.theta = _short_closed
                except Exception:
                    pass
        # Capa GLOW: añadir 2 trazas con líneas anchas semi-transparentes,
        # luego reordenar (permutación) para que estén DETRÁS del trazo
        # principal. Buscamos la traza con los valores reales (no la
        # circular de range 20).
        try:
            data_trace_idx = None
            for i, tr in enumerate(sf_fig.data):
                r_vals = getattr(tr, "r", None) or ()
                # La traza de datos NO es la circular de "20s"
                if r_vals and not all(v == 20 for v in r_vals):
                    data_trace_idx = i
                    break
            if data_trace_idx is not None:
                src = sf_fig.data[data_trace_idx]
                r, theta = src.r, src.theta
                # Outer glow — añadir y luego mover delante
                sf_fig.add_trace(go.Scatterpolar(
                    r=r, theta=theta, mode="lines",
                    line=dict(color="rgba(255,184,77,0.18)", width=28,
                              shape="spline", smoothing=0.4),
                    fill="toself", fillcolor="rgba(0,0,0,0)",
                    showlegend=False, hoverinfo="skip",
                ))
                sf_fig.add_trace(go.Scatterpolar(
                    r=r, theta=theta, mode="lines",
                    line=dict(color="rgba(255,184,77,0.32)", width=14,
                              shape="spline", smoothing=0.4),
                    fill="toself", fillcolor="rgba(0,0,0,0)",
                    showlegend=False, hoverinfo="skip",
                ))
                # Reordenar — glow traces (los 2 últimos) van al inicio
                n = len(sf_fig.data)
                glow_idx = (n - 2, n - 1)
                rest_idx = tuple(i for i in range(n) if i not in glow_idx)
                new_order = glow_idx + rest_idx
                sf_fig.data = tuple(sf_fig.data[i] for i in new_order)
        except Exception:
            pass

        sf_fig.update_layout(
            paper_bgcolor="#141920", plot_bgcolor="#141920",
            # Margins XL para que CRECIMIENTO/MOMENTUM/VALOR quepan completos
            margin=dict(l=420, r=420, t=320, b=320),
            font=dict(family="Helvetica Neue, Helvetica, sans-serif",
                      color="#E4E7EC", size=110),
            showlegend=False,
            polar=dict(
                bgcolor="#0F141A",
                angularaxis=dict(
                    # tickfont 110px — al embebed a 580pt da ~22pt visible
                    tickfont=dict(size=110, color="#FFB84D",
                                  family="Helvetica Neue, Helvetica"),
                    linecolor="rgba(255,184,77,0.6)",
                    gridcolor="#1E2530",
                ),
                radialaxis=dict(
                    tickfont=dict(size=44, color="#7A8898"),
                    gridcolor="#1E2530",
                    showline=False,
                    range=[0, 20],
                ),
            ),
        )
        # Refuerzo de la línea principal (la última traza, dibujada encima)
        try:
            main_idx = len(sf_fig.data) - 1
            sf_fig.data[main_idx].line = dict(color="#FFB84D", width=6,
                                              shape="spline", smoothing=0.4)
            sf_fig.data[main_idx].marker = dict(size=22, color="#FFD740",
                                                line=dict(width=3, color="white"))
            sf_fig.data[main_idx].fillcolor = "rgba(255,184,77,0.30)"
        except Exception:
            pass
        # Render a mayor resolución para que las labels enormes salgan nítidas
        sf_png = _chart_png(sf_fig, width_px=2000, height_px=2000)
        if sf_png:
            sf_size = min(panel_w - 60, mid_h - 110)
            sf_x = p2_x + (panel_w - sf_size) / 2
            sf_y = _y(mid_top + mid_h - 20)
            c.drawImage(sf_png, sf_x, sf_y,
                        width=sf_size, height=sf_size,
                        preserveAspectRatio=True, mask='auto')
    except Exception:
        sn = a.snowflake or {}
        ty = mid_top + 110
        for k in ("value", "quality", "growth", "momentum", "future"):
            v = _to_float(sn.get(k, 0), default=0.0)
            _text(c, k.upper(), p2_x + 50, ty, font=FONT_DISPLAY, size=14, color=TEXT_LO)
            _text(c, f"{v:.1f} / 20", p2_x + panel_w - 50, ty,
                  font=FONT_DISPLAY_XL, size=16, color=ORANGE, anchor="right")
            ty += 60

    # ── PANEL 3 — DESGLOSE POR ANÁLISIS (8 agentes horizontal bars) ──
    p3_x = p2_x + panel_w + gap_card
    _box(c, p3_x, mid_top, panel_w, mid_h, r=12,
         fill=BG_CARD, stroke=BORDER, stroke_w=1)
    _text(c, "DESGLOSE POR ANÁLISIS", p3_x + 28, mid_top + 38,
          font=FONT_DISPLAY, size=19, color=TEXT_LO)
    _text(c, "8 AGENTES · 0–100 c/u", p3_x + 28, mid_top + 64,
          font=FONT_REG, size=14, color=TEXT_DIM)

    try:
        from dashboard.charts import build_score_breakdown
        sb_fig = build_score_breakdown(a.score_breakdown or {})
        sb_fig.update_layout(
            paper_bgcolor="#141920", plot_bgcolor="#141920",
            # Margin izquierda XL para que los nombres de los agentes
            # (Fundamentales, Catalizadores, Sentimiento) quepan completos
            margin=dict(l=560, r=200, t=60, b=80),
            font=dict(family="Helvetica Neue, Helvetica, sans-serif",
                      color="#E4E7EC", size=80),
            xaxis=dict(showgrid=True, gridcolor="#1E2530",
                       tickfont=dict(size=56, color="#7A8898"),
                       range=[0, 100], zeroline=False),
            yaxis=dict(tickfont=dict(size=80, color="#E4E7EC",
                                     family="Helvetica Neue, Helvetica")),
            height=720,
            showlegend=False,
            bargap=0.18,  # barras más gruesas
        )
        try:
            # Glow: bordes blancos GRUESOS + opacidad full + texto enorme
            sb_fig.update_traces(
                textposition="inside",
                insidetextanchor="middle",
                textfont=dict(size=72, color="white",
                              family="Helvetica Neue, Helvetica"),
                opacity=1.0,
                marker=dict(line=dict(width=10,
                                       color="rgba(255,255,255,0.25)")),
            )
        except Exception:
            pass
        sb_png = _chart_png(sb_fig, width_px=2000, height_px=2000)
        if sb_png:
            cw = panel_w - 40
            ch = mid_h - 100
            c.drawImage(sb_png, p3_x + 20, _y(mid_top + mid_h - 20),
                        width=cw, height=ch,
                        preserveAspectRatio=True, mask='auto')
    except Exception:
        sb = a.score_breakdown or {}
        labels = [
            ("Fundamentales", sb.get("fundamentals", 50)),
            ("Técnico",       sb.get("technical",    50)),
            ("Futuro",        sb.get("future",       50)),
            ("Smart Money",   sb.get("institutional",50)),
            ("Catalizadores", sb.get("catalysts",    50)),
            ("Macro",         sb.get("macro",        50)),
            ("Sentimiento",   sb.get("sentiment",    50)),
            ("Riesgo",        sb.get("risk",         50)),
        ]
        by = mid_top + 100
        bw_max = panel_w - 200
        for lbl, sc in labels:
            s = _to_float(sc, default=50.0)
            col = _score_color(s)
            _text(c, lbl, p3_x + 20, by + 12, font=FONT_DISPLAY, size=12, color=TEXT_MD)
            c.setFillColor(col)
            c.roundRect(p3_x + 150, _y(by + 16), bw_max * s/100, 12, 3, fill=1, stroke=0)
            _text(c, f"{s:.0f}", p3_x + 150 + bw_max + 16, by + 12,
                  font=FONT_DISPLAY_XL, size=13, color=col)
            by += 42

    # ── FOOTER: 5 KPI TILES ─────────────────────────────────────────────
    foot_top = mid_top + mid_h + 22
    foot_h = 160

    entry_f  = _to_float(a.entry_price)
    stop_f   = _to_float(a.stop_loss)
    target_f = _to_float(a.target_price)

    def fmt_money(v):
        f = _to_float(v)
        return f"${f:,.2f}" if f is not None else "—"

    risk_pct = None
    if entry_f and stop_f:
        try: risk_pct = (entry_f - stop_f) / entry_f * 100
        except Exception: risk_pct = None
    reward_pct = None
    if entry_f and target_f:
        try: reward_pct = (target_f - entry_f) / entry_f * 100
        except Exception: reward_pct = None

    stop_sub = f"hasta −{abs(risk_pct):.1f}%" if risk_pct else ""
    tgt_sub  = f"hasta +{reward_pct:.1f}%" if reward_pct else ""

    # SOLO 3 tiles: Precio Actual / Precio Mínimo / Precio Potencial
    # Sin R/R, sin Sizing, sin terminología de trading.
    tiles = [
        ("PRECIO ACTUAL",     fmt_money(a.entry_price),  ORANGE, "del último cierre"),
        ("PRECIO MÍNIMO",     fmt_money(a.stop_loss),    RED,    stop_sub or "potencial"),
        ("PRECIO POTENCIAL",  fmt_money(a.target_price), GREEN,  tgt_sub or "objetivo"),
    ]
    gap = 24
    total_w = PAGE_W - 2 * MARGIN_X
    tw = (total_w - gap * 2) / 3
    for i, (label, value, color, sub) in enumerate(tiles):
        x = MARGIN_X + i * (tw + gap)
        _box(c, x, foot_top, tw, foot_h, r=12,
             fill=BG_CARD, stroke=color, stroke_w=1.5)
        # Accent strip top
        c.setFillColor(color)
        c.rect(x, _y(foot_top + 5), tw, 5, fill=1, stroke=0)
        _text(c, label, x + tw/2, foot_top + 46,
              font=FONT_DISPLAY, size=20, color=TEXT_LO, anchor="center")
        _text(c, value, x + tw/2, foot_top + 105,
              font=FONT_DISPLAY_XL, size=48, color=color, anchor="center")
        if sub:
            _text(c, sub, x + tw/2, foot_top + 138,
                  font=FONT_REG, size=15, color=TEXT_LO, anchor="center")

    # Disclaimer
    _text(c, "Análisis educativo · No constituye recomendación de inversión",
          PAGE_W/2, PAGE_H - 22,
          font=FONT_REG, size=9, color=TEXT_DIM, anchor="center")


# ═════════════════════════════════════════════════════════════════════════
#               PÁGINA 2 — FUNDAMENTALES + TENDENCIA TÉCNICA SIMPLE
# ═════════════════════════════════════════════════════════════════════════

def _verdict_stability(score):
    """Devuelve (texto, color) describiendo qué tan estable/fragil es la
    empresa en lenguaje simple para inversor principiante."""
    s = _to_float(score, default=50.0)
    if s >= 80: return "Empresa muy estable y rentable", GREEN
    if s >= 65: return "Empresa estable con buenas finanzas", GREEN
    if s >= 50: return "Empresa con bases sólidas pero mejorable", ORANGE
    if s >= 35: return "Empresa con algunas fragilidades visibles", ORANGE
    return "Empresa con fragilidades importantes", RED


def _verdict_trend(score, stage_value):
    """Veredicto simple sobre la tendencia del precio."""
    s = _to_float(score, default=50.0)
    stage = str(stage_value or "").lower()
    if "2" in stage or s >= 70: return "Tendencia alcista clara", GREEN
    if "3" in stage: return "Distribución — momentum agotándose", ORANGE
    if "4" in stage or s < 35: return "Tendencia bajista en curso", RED
    if s >= 55: return "Tendencia alcista moderada", GREEN
    if s >= 45: return "Tendencia lateral — sin dirección clara", ORANGE
    return "Tendencia débil o bajista", RED


def _build_simple_price_chart(a):
    """Crea un Plotly chart de LÍNEA SIMPLE con glow + gradient fill.
    No velas, no indicadores — solo la tendencia del precio. Para inversor
    principiante-intermedio."""
    import plotly.graph_objects as go

    tech = (a.reports or {}).get("technical")
    if not tech or not tech.raw_data:
        return None
    df = tech.raw_data.get("df_daily", {}) or {}
    close = df.get("Close", {})
    if not close:
        return None

    # Ordenar por fecha
    dates_sorted = sorted(close.keys())
    series = [(d, _to_float(close[d])) for d in dates_sorted]
    series = [(d, p) for d, p in series if p is not None]
    if len(series) < 20:
        return None
    dates = [s[0] for s in series]
    prices = [s[1] for s in series]

    fig = go.Figure()

    # Capa 1 — glow exterior (línea muy gruesa, alfa bajo)
    fig.add_trace(go.Scatter(
        x=dates, y=prices,
        mode="lines",
        line=dict(color="rgba(255,184,77,0.18)", width=24,
                  shape="spline", smoothing=0.5),
        hoverinfo="skip", showlegend=False,
    ))
    # Capa 2 — glow interno
    fig.add_trace(go.Scatter(
        x=dates, y=prices,
        mode="lines",
        line=dict(color="rgba(255,184,77,0.35)", width=12,
                  shape="spline", smoothing=0.5),
        hoverinfo="skip", showlegend=False,
    ))
    # Capa 3 — fill gradient debajo
    fig.add_trace(go.Scatter(
        x=dates, y=prices,
        mode="lines",
        line=dict(color="#FFB84D", width=5,
                  shape="spline", smoothing=0.5),
        fill="tozeroy",
        fillcolor="rgba(255,184,77,0.10)",
        hoverinfo="skip", showlegend=False,
    ))
    # Marker del precio actual
    fig.add_trace(go.Scatter(
        x=[dates[-1]], y=[prices[-1]],
        mode="markers",
        marker=dict(size=24, color="#FFD740",
                    line=dict(width=5, color="white")),
        hoverinfo="skip", showlegend=False,
    ))

    min_p, max_p = min(prices), max(prices)
    pad = (max_p - min_p) * 0.12
    fig.update_layout(
        paper_bgcolor="#141920", plot_bgcolor="#141920",
        margin=dict(l=110, r=80, t=50, b=60),
        font=dict(family="Helvetica", color="#E4E7EC", size=24),
        xaxis=dict(
            showgrid=False, showline=False,
            tickfont=dict(size=20, color="#7A8898"),
            tickformat="%b %Y", nticks=6,
        ),
        yaxis=dict(
            showgrid=True, gridcolor="#1E2530", gridwidth=1,
            tickfont=dict(size=20, color="#7A8898"),
            tickprefix="$", range=[max(0, min_p - pad), max_p + pad],
        ),
        showlegend=False,
    )
    return fig


def _page_2_finance_technical(c, a):
    _fill_bg(c)

    # ── HEADER ──────────────────────────────────────────────────────────
    _text(c, "FUNDAMENTALES Y TENDENCIA", MARGIN_X, MARGIN_Y + 52,
          font=FONT_DISPLAY_XL, size=44, color=TEXT_HI)
    _text(c, f"{a.ticker}   ·   {_safe(a.company_name)[:40]}",
          MARGIN_X, MARGIN_Y + 88,
          font=FONT_BOLD, size=19, color=ORANGE)
    sc_f = _to_float(a.composite_score)
    _text(c, f"PUNTAJE GENERAL   {sc_f:.1f}  /  100" if sc_f is not None else "PUNTAJE GENERAL   —  /  100",
          PAGE_W - MARGIN_X, MARGIN_Y + 62,
          font=FONT_DISPLAY, size=30,
          color=_score_color(sc_f if sc_f is not None else 50), anchor="right")

    c.setStrokeColor(ORANGE)
    c.setLineWidth(1)
    c.line(MARGIN_X, _y(MARGIN_Y + 108), PAGE_W - MARGIN_X, _y(MARGIN_Y + 108))

    # ── LAYOUT: 2 COLUMNAS DE ALTURA COMPLETA ───────────────────────────
    top_y = MARGIN_Y + 126
    avail_h = PAGE_H - top_y - MARGIN_Y - 30
    col_gap = 24
    col_w = (PAGE_W - 2 * MARGIN_X - col_gap) / 2

    # ════════ COL IZQUIERDA — FUNDAMENTALES (estabilidad financiera) ════
    fx = MARGIN_X
    _box(c, fx, top_y, col_w, avail_h, r=14,
         fill=BG_CARD, stroke=BORDER, stroke_w=1)
    # Accent strip top
    fund_rpt = (a.reports or {}).get("fundamentals")
    fund_score = _to_float(fund_rpt.score, default=50.0) if fund_rpt else 50.0
    fund_color = _score_color(fund_score)
    c.setFillColor(fund_color)
    c.rect(fx, _y(top_y + 5), col_w, 5, fill=1, stroke=0)

    _text(c, "FUNDAMENTALES", fx + 32, top_y + 50,
          font=FONT_DISPLAY_XL, size=30, color=TEXT_HI)
    _text(c, "Qué tan estable y rentable es la empresa",
          fx + 32, top_y + 82,
          font=FONT_REG, size=17, color=TEXT_LO)

    # Score grande arriba a la derecha
    _text(c, f"{fund_score:.0f}", fx + col_w - 32, top_y + 60,
          font=FONT_DISPLAY_XL, size=58, color=fund_color, anchor="right")
    _text(c, "DE 100", fx + col_w - 32, top_y + 92,
          font=FONT_DISPLAY, size=14, color=TEXT_LO, anchor="right")

    # Veredicto en banda destacada
    verdict_text, verdict_col = _verdict_stability(fund_score)
    vb_top = top_y + 120
    vb_h = 66
    _box(c, fx + 24, vb_top, col_w - 48, vb_h, r=10,
         fill=BG_CARD2, stroke=verdict_col, stroke_w=1)
    c.setFillColor(verdict_col)
    c.circle(fx + 54, _y(vb_top + vb_h/2), 8, fill=1, stroke=0)
    _text(c, verdict_text, fx + 76, vb_top + vb_h/2 + 7,
          font=FONT_DISPLAY, size=22, color=verdict_col)

    # Métricas clave (2 columnas × 3 filas = 6 KPIs)
    km = (fund_rpt.key_metrics or {}) if fund_rpt else {}

    def _km_lookup(*keys, default="—"):
        for k in keys:
            v = km.get(k)
            if v not in (None, "", "N/A"):
                s = str(v).strip()
                # Limpiar si trae "/" o "("
                if "/" in s: s = s.split("/")[0].strip()
                if "(" in s: s = s.split("(")[0].strip()
                if len(s) > 14: s = s[:13] + "…"
                return s
        return default

    metrics = [
        ("Crecimiento ingresos", _km_lookup("revenue_growth", "revenue_growth_yoy",
                                            "revenue_growth_pct", "growth"),
         "interno anual"),
        ("Rentabilidad capital", _km_lookup("roic", "roic_pct", "roe"),
         "cuánto produce el capital"),
        ("Múltiplo precio/ganancia", _km_lookup("forward_pe", "pe_forward", "pe_ratio"),
         "lo que pagas por cada $1"),
        ("Margen operativo", _km_lookup("operating_margin", "operating_margins"),
         "$ que queda de cada venta"),
        ("Deuda / patrimonio", _km_lookup("debt_equity", "debt_to_equity", "de_ratio"),
         "cuánto debe vs lo que tiene"),
        ("Liquidez corriente", _km_lookup("current_ratio", "current_ratio_yf"),
         "capacidad pago corto plazo"),
    ]

    m_top = vb_top + vb_h + 30
    m_gap_x = 18
    m_gap_y = 14
    m_cols = 2
    m_rows = 3
    m_card_w = (col_w - 48 - m_gap_x) / m_cols
    m_card_h = (avail_h - (vb_top - top_y) - vb_h - 50 - m_gap_y * (m_rows - 1)) / m_rows

    for i, (label, value, sub) in enumerate(metrics):
        r_ix = i // m_cols
        c_ix = i % m_cols
        mx = fx + 24 + c_ix * (m_card_w + m_gap_x)
        my = m_top + r_ix * (m_card_h + m_gap_y)
        _box(c, mx, my, m_card_w, m_card_h, r=10,
             fill=BG_CARD2, stroke=BORDER, stroke_w=1)
        _text(c, label, mx + 20, my + 32,
              font=FONT_DISPLAY, size=15, color=TEXT_LO)
        _text(c, str(value), mx + 20, my + 70,
              font=FONT_DISPLAY_XL, size=34, color=TEXT_HI)
        _text(c, sub, mx + 20, my + 96,
              font=FONT_REG, size=13, color=TEXT_DIM)

    # ════════ COL DERECHA — TENDENCIA TÉCNICA SIMPLE ════════════════════
    tx_x = MARGIN_X + col_w + col_gap
    _box(c, tx_x, top_y, col_w, avail_h, r=14,
         fill=BG_CARD, stroke=BORDER, stroke_w=1)
    tech_rpt = (a.reports or {}).get("technical")
    tech_score = _to_float(tech_rpt.score, default=50.0) if tech_rpt else 50.0
    tech_color = _score_color(tech_score)
    c.setFillColor(tech_color)
    c.rect(tx_x, _y(top_y + 5), col_w, 5, fill=1, stroke=0)

    _text(c, "TENDENCIA DEL PRECIO", tx_x + 32, top_y + 50,
          font=FONT_DISPLAY_XL, size=30, color=TEXT_HI)
    _text(c, "Cómo viene moviéndose en el último año",
          tx_x + 32, top_y + 82,
          font=FONT_REG, size=17, color=TEXT_LO)
    _text(c, f"{tech_score:.0f}", tx_x + col_w - 32, top_y + 60,
          font=FONT_DISPLAY_XL, size=58, color=tech_color, anchor="right")
    _text(c, "DE 100", tx_x + col_w - 32, top_y + 92,
          font=FONT_DISPLAY, size=14, color=TEXT_LO, anchor="right")

    # Veredicto técnico
    stage_val = (tech_rpt.key_metrics or {}).get("stage", "") if tech_rpt else ""
    vt_text, vt_col = _verdict_trend(tech_score, stage_val)
    vtb_top = top_y + 120
    vtb_h = 66
    _box(c, tx_x + 24, vtb_top, col_w - 48, vtb_h, r=10,
         fill=BG_CARD2, stroke=vt_col, stroke_w=1)
    c.setFillColor(vt_col)
    c.circle(tx_x + 54, _y(vtb_top + vtb_h/2), 8, fill=1, stroke=0)
    _text(c, vt_text, tx_x + 76, vtb_top + vtb_h/2 + 7,
          font=FONT_DISPLAY, size=22, color=vt_col)

    # Chart de línea
    chart_top = vtb_top + vtb_h + 22
    chart_h = avail_h - (vtb_top - top_y) - vtb_h - 100
    try:
        pc_fig = _build_simple_price_chart(a)
        if pc_fig is not None:
            pc_fig.update_layout(height=int(chart_h * 1.5))
            pc_png = _chart_png(pc_fig, width_px=1400, height_px=int(chart_h * 1.5))
            if pc_png:
                cw = col_w - 40
                c.drawImage(pc_png, tx_x + 20, _y(chart_top + chart_h),
                            width=cw, height=chart_h,
                            preserveAspectRatio=True, mask='auto')
    except Exception:
        _text(c, "Chart de precio no disponible",
              tx_x + col_w/2, chart_top + chart_h/2,
              font=FONT_REG, size=14, color=TEXT_DIM, anchor="center")

    # Precio actual destacado debajo del chart
    cur_price = _to_float(a.entry_price)
    if cur_price is not None:
        cp_top = chart_top + chart_h + 14
        _text(c, "PRECIO ACTUAL", tx_x + 32, cp_top + 14,
              font=FONT_DISPLAY, size=14, color=TEXT_LO)
        _text(c, f"${cur_price:,.2f}", tx_x + 32, cp_top + 56,
              font=FONT_DISPLAY_XL, size=36, color=ORANGE)

    # ── Disclaimer ──────────────────────────────────────────────────────
    _text(c, "Análisis educativo · No constituye recomendación de inversión",
          PAGE_W/2, PAGE_H - 22,
          font=FONT_REG, size=9, color=TEXT_DIM, anchor="center")


# ═════════════════════════════════════════════════════════════════════════
#                       PÁGINA 3 — PILARES DEL ANÁLISIS
# ═════════════════════════════════════════════════════════════════════════
def _page_3_pillars(c, a):
    _fill_bg(c)

    # ── HEADER ──────────────────────────────────────────────────────────
    _text(c, "ANÁLISIS POR DIMENSIONES", MARGIN_X, MARGIN_Y + 52,
          font=FONT_DISPLAY_XL, size=44, color=TEXT_HI)
    _text(c, f"{a.ticker}   ·   {_safe(a.company_name)[:40]}",
          MARGIN_X, MARGIN_Y + 88,
          font=FONT_BOLD, size=19, color=ORANGE)
    sc_f = _to_float(a.composite_score)
    _text(c, f"PUNTAJE GENERAL   {sc_f:.1f}  /  100" if sc_f is not None else "PUNTAJE GENERAL   —  /  100",
          PAGE_W - MARGIN_X, MARGIN_Y + 62,
          font=FONT_DISPLAY, size=30,
          color=_score_color(sc_f if sc_f is not None else 50), anchor="right")

    c.setStrokeColor(ORANGE)
    c.setLineWidth(1)
    c.line(MARGIN_X, _y(MARGIN_Y + 108), PAGE_W - MARGIN_X, _y(MARGIN_Y + 108))

    # ── SCOREBOARD HORIZONTAL (8 pills, mucho más legible que un bar chart) ──
    sb_top = MARGIN_Y + 126
    sb_h = 120
    _box(c, MARGIN_X, sb_top, PAGE_W - 2*MARGIN_X, sb_h, r=12,
         fill=BG_CARD, stroke=BORDER, stroke_w=1)
    _text(c, "SCORES  ·  8 DIMENSIONES",
          MARGIN_X + 32, sb_top + 34,
          font=FONT_DISPLAY, size=17, color=ORANGE)

    # 8 pills colocadas horizontalmente, color por score
    sb = a.score_breakdown or {}
    score_pills = [
        ("Fundamentales", sb.get("fundamentals", 50)),
        ("Técnico",       sb.get("technical",    50)),
        ("Futuro",        sb.get("future",       50)),
        ("Smart Money",   sb.get("institutional",50)),
        ("Catalizadores", sb.get("catalysts",    50)),
        ("Macro",         sb.get("macro",        50)),
        ("Sentimiento",   sb.get("sentiment",    50)),
        ("Riesgo",        sb.get("risk",         50)),
    ]
    pill_gap = 14
    pill_total_w = PAGE_W - 2*MARGIN_X - 60
    pill_w = (pill_total_w - pill_gap * 7) / 8
    pill_h = 54
    pill_y_top = sb_top + 50

    for i, (label, score) in enumerate(score_pills):
        s = _to_float(score, default=50.0)
        col = _score_color(s)
        px = MARGIN_X + 30 + i * (pill_w + pill_gap)
        # Pill body
        _box(c, px, pill_y_top, pill_w, pill_h, r=8,
             fill=BG_CARD2, stroke=col, stroke_w=1.5)
        # Accent left bar
        c.setFillColor(col)
        c.rect(px, _y(pill_y_top + pill_h), 4, pill_h, fill=1, stroke=0)
        # Score grande
        _text(c, f"{s:.0f}", px + 16, pill_y_top + 40,
              font=FONT_DISPLAY_XL, size=30, color=col)
        # Label arriba derecha
        _text(c, label.upper(), px + pill_w - 10, pill_y_top + 22,
              font=FONT_DISPLAY, size=12, color=TEXT_LO, anchor="right")
        _text(c, "/100", px + pill_w - 10, pill_y_top + 44,
              font=FONT_BOLD, size=12, color=TEXT_LO, anchor="right")

    # ── GRID 4×2 — LOS 8 AGENTES CON INSIGHT NARRATIVO ──────────────────
    grid_top = sb_top + sb_h + 26
    grid_h = PAGE_H - grid_top - MARGIN_Y - 30
    cols, rows = 4, 2
    cgap = 18
    card_w = (PAGE_W - 2*MARGIN_X - cgap*(cols-1)) / cols
    card_h = (grid_h - cgap*(rows-1)) / rows

    reports = a.reports or {}

    def km(rpt, *keys):
        if not rpt:
            return "—"
        for k in keys:
            v = (rpt.key_metrics or {}).get(k)
            if v not in (None, "", "N/A"):
                s = str(v).strip()
                # Truncación fuerte — los KPIs en card deben ser cortos
                # (el orquestador a veces guarda "Stage 2 diario / Stage 4 semanal")
                if len(s) > 14:
                    # Si contiene '/', quedarse con la primera parte
                    if "/" in s:
                        s = s.split("/")[0].strip()
                    # Si contiene '(', quedarse antes del paréntesis
                    if "(" in s:
                        s = s.split("(")[0].strip()
                    # Hard-cap 14 chars
                    if len(s) > 14:
                        s = s[:13].rstrip(",;: ") + "…"
                return s
        return "—"

    def first_pro(rpt):
        if not rpt or not rpt.pros:
            return ""
        return str(rpt.pros[0])

    # 8 agentes — uno por card. Cada tupla:
    # (title, símbolo, report_key, key_metric_label, key_metric_value_lookup)
    cards = [
        ("FUNDAMENTALES",   "◉", "fundamentals",
         "P/E FWD", km(reports.get("fundamentals"), "forward_pe", "pe_forward", "pe_ratio"),
         "ROIC",    km(reports.get("fundamentals"), "roic", "roic_pct", "roe")),
        ("TÉCNICO",         "▲", "technical",
         "STAGE",   km(reports.get("technical"), "stage", "stage_minervini", "minervini_stage"),
         "RSI 14",  km(reports.get("technical"), "rsi", "rsi_14")),
        ("VIAB. FUTURA",    "◇", "future",
         "MOAT",    km(reports.get("future"), "moat_strength", "moat", "moat_quality"),
         "DISRUPCIÓN", km(reports.get("future"), "disruption_risk", "disruption")),
        ("SMART MONEY",     "⬢", "institutional",
         "INSTITUCIONAL", km(reports.get("institutional"), "institutional_ownership", "inst_ownership_pct", "ownership"),
         "INSIDERS", km(reports.get("institutional"), "insider_signal", "insider_buying", "insider_activity")),
        ("CATALIZADORES",   "✦", "catalysts",
         "PRÓX. EARN.", km(reports.get("catalysts"), "next_earnings_days", "days_to_earnings", "next_earnings"),
         "BEAT RATE", km(reports.get("catalysts"), "beat_rate", "earnings_beat_rate")),
        ("MACRO & SECTOR",  "⊕", "macro",
         "ENTORNO", km(reports.get("macro"), "market_environment", "market_env", "regime"),
         "SECTOR",  km(reports.get("macro"), "sector_momentum", "sector_perf", "sector")),
        ("SENTIMIENTO",     "◐", "sentiment",
         "NARRATIVA", km(reports.get("sentiment"), "narrative", "dominant_theme", "narrative_theme"),
         "MOMENTUM", km(reports.get("sentiment"), "sentiment_momentum", "sentiment_trend", "momentum")),
        ("RIESGO & SIZING", "◈", "risk",
         "R/R", _extract_ratio(a.risk_reward),
         "SIZING", (lambda f: f"{f:.1f}%" if f is not None else "—")(_to_float(a.position_size_pct))),
    ]

    for i, (title, sym, rkey, m1_lbl, m1_val, m2_lbl, m2_val) in enumerate(cards):
        r_ix = i // cols
        col_ix = i % cols
        cx = MARGIN_X + col_ix * (card_w + cgap)
        ctop = grid_top + r_ix * (card_h + cgap)
        rpt = reports.get(rkey)
        score = _to_float(rpt.score, default=50.0) if rpt else 50.0
        sc_color = _score_color(score)

        # Card background
        _box(c, cx, ctop, card_w, card_h, r=10,
             fill=BG_CARD, stroke=BORDER, stroke_w=1)
        # Accent strip top en el color del score
        c.setFillColor(sc_color)
        c.rect(cx, _y(ctop + 4), card_w, 4, fill=1, stroke=0)

        # ── HEADER de card (compacto) ──
        _text(c, sym, cx + 22, ctop + 42,
              font=FONT_BOLD, size=26, color=sc_color)
        _text(c, title, cx + 54, ctop + 40,
              font=FONT_DISPLAY, size=20, color=TEXT_HI)
        _text(c, f"{score:.0f}", cx + card_w - 24, ctop + 42,
              font=FONT_DISPLAY_XL, size=32, color=sc_color, anchor="right")
        _text(c, "/100", cx + card_w - 24, ctop + 60,
              font=FONT_BOLD, size=12, color=TEXT_LO, anchor="right")

        # Divider sutil
        c.setStrokeColor(BORDER)
        c.setLineWidth(0.5)
        c.line(cx + 20, _y(ctop + 66), cx + card_w - 20, _y(ctop + 66))

        # ── KEY METRICS (1 línea con 2 KPIs) ──
        _text(c, m1_lbl, cx + 22, ctop + 92,
              font=FONT_DISPLAY, size=14, color=TEXT_LO)
        _text(c, str(m1_val), cx + 22, ctop + 120,
              font=FONT_DISPLAY, size=22, color=TEXT_HI)
        _text(c, m2_lbl, cx + card_w - 24, ctop + 92,
              font=FONT_DISPLAY, size=14, color=TEXT_LO, anchor="right")
        _text(c, str(m2_val), cx + card_w - 24, ctop + 120,
              font=FONT_DISPLAY, size=22, color=TEXT_HI, anchor="right")

        # Subdivider entre metrics e insight
        c.setStrokeColor(BORDER)
        c.setLineWidth(0.3)
        c.line(cx + 20, _y(ctop + 136), cx + card_w - 20, _y(ctop + 136))

        # ── INSIGHT NARRATIVO (más grande con espacio extra) ──
        insight = _extract_insight(rpt, max_chars=260)
        if insight:
            _text(c, "“", cx + 22, ctop + 176,
                  font=FONT_DISPLAY_XL, size=38, color=ORANGE)
            _wrap(c, insight, cx + 54, ctop + 168,
                  width=card_w - 76, font=FONT_REG, size=18,
                  color=TEXT_MD, line_height=1.4, max_lines=4)
        else:
            _text(c, "Insight no disponible para este análisis.",
                  cx + card_w/2, ctop + 200,
                  font=FONT_REG, size=16, color=TEXT_DIM, anchor="center")

        # ── PRO destacado al pie ──
        pro = first_pro(rpt)
        if pro:
            pro_y = ctop + card_h - 26
            c.setFillColor(GREEN)
            c.circle(cx + 26, _y(pro_y - 5), 5, fill=1, stroke=0)
            _wrap(c, pro, cx + 42, pro_y,
                  width=card_w - 62, font=FONT_REG, size=14,
                  color=TEXT_LO, line_height=1.3, max_lines=1)

    # Footer disclaimer
    _text(c, "Análisis educativo · Vocabulario de inversión, no trading · No constituye recomendación",
          PAGE_W/2, PAGE_H - 22,
          font=FONT_REG, size=9, color=TEXT_DIM, anchor="center")


# ═════════════════════════════════════════════════════════════════════════
#       PÁGINA 4 — FORTALEZAS/DEBILIDADES + CHART PRECIOS + CTA BANNER
# ═════════════════════════════════════════════════════════════════════════

def _build_price_journey_chart(a):
    """Chart de línea simple + líneas horizontales para precio mín/actual/potencial."""
    import plotly.graph_objects as go
    tech = (a.reports or {}).get("technical")
    if not tech or not tech.raw_data: return None
    df = tech.raw_data.get("df_daily", {}) or {}
    close = df.get("Close", {})
    if not close: return None
    dates_sorted = sorted(close.keys())
    series = [(d, _to_float(close[d])) for d in dates_sorted]
    series = [(d, p) for d, p in series if p is not None]
    if len(series) < 20: return None
    dates = [s[0] for s in series]
    prices = [s[1] for s in series]

    cur_f  = _to_float(a.entry_price)
    min_f  = _to_float(a.stop_loss)
    pot_f  = _to_float(a.target_price)

    fig = go.Figure()
    # Glow exterior + interior + línea + fill (igual que el simple chart)
    fig.add_trace(go.Scatter(x=dates, y=prices, mode="lines",
        line=dict(color="rgba(255,184,77,0.18)", width=24, shape="spline", smoothing=0.5),
        hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(x=dates, y=prices, mode="lines",
        line=dict(color="rgba(255,184,77,0.35)", width=12, shape="spline", smoothing=0.5),
        hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(x=dates, y=prices, mode="lines",
        line=dict(color="#FFB84D", width=5, shape="spline", smoothing=0.5),
        fill="tozeroy", fillcolor="rgba(255,184,77,0.10)",
        hoverinfo="skip", showlegend=False))
    # Marker del precio actual
    fig.add_trace(go.Scatter(x=[dates[-1]], y=[prices[-1]], mode="markers",
        marker=dict(size=26, color="#FFD740", line=dict(width=5, color="white")),
        hoverinfo="skip", showlegend=False))

    # Líneas horizontales para min/actual/potencial
    shapes = []
    annotations = []
    last_date = dates[-1]
    if cur_f is not None:
        shapes.append(dict(type="line", x0=dates[0], x1=last_date,
                            y0=cur_f, y1=cur_f, xref="x", yref="y",
                            line=dict(color="#FFB84D", width=2, dash="dot")))
        annotations.append(dict(x=1, xref="paper", y=cur_f, yref="y",
                                xanchor="left", yanchor="middle",
                                text=f"  <b>Actual</b><br>  ${cur_f:,.0f}",
                                showarrow=False,
                                font=dict(size=22, color="#FFB84D",
                                          family="Helvetica-Bold")))
    if min_f is not None:
        shapes.append(dict(type="line", x0=dates[0], x1=last_date,
                            y0=min_f, y1=min_f, xref="x", yref="y",
                            line=dict(color="#FF3B5C", width=2, dash="dash")))
        annotations.append(dict(x=1, xref="paper", y=min_f, yref="y",
                                xanchor="left", yanchor="middle",
                                text=f"  <b>Mínimo</b><br>  ${min_f:,.0f}",
                                showarrow=False,
                                font=dict(size=22, color="#FF3B5C",
                                          family="Helvetica-Bold")))
    if pot_f is not None:
        shapes.append(dict(type="line", x0=dates[0], x1=last_date,
                            y0=pot_f, y1=pot_f, xref="x", yref="y",
                            line=dict(color="#00FF88", width=2, dash="dash")))
        annotations.append(dict(x=1, xref="paper", y=pot_f, yref="y",
                                xanchor="left", yanchor="middle",
                                text=f"  <b>Potencial</b><br>  ${pot_f:,.0f}",
                                showarrow=False,
                                font=dict(size=22, color="#00FF88",
                                          family="Helvetica-Bold")))

    all_pts = prices + [v for v in (cur_f, min_f, pot_f) if v is not None]
    min_p, max_p = min(all_pts), max(all_pts)
    pad = (max_p - min_p) * 0.08
    fig.update_layout(
        paper_bgcolor="#141920", plot_bgcolor="#141920",
        margin=dict(l=110, r=200, t=40, b=60),
        font=dict(family="Helvetica", color="#E4E7EC", size=22),
        xaxis=dict(showgrid=False, showline=False,
                   tickfont=dict(size=20, color="#7A8898"),
                   tickformat="%b %Y", nticks=6),
        yaxis=dict(showgrid=True, gridcolor="#1E2530",
                   tickfont=dict(size=20, color="#7A8898"),
                   tickprefix="$",
                   range=[max(0, min_p - pad), max_p + pad]),
        showlegend=False,
        shapes=shapes,
        annotations=annotations,
    )
    return fig


def _page_4_finale(c, a):
    _fill_bg(c)

    # ── HEADER ──────────────────────────────────────────────────────────
    _text(c, "VEREDICTO Y CONCLUSIONES", MARGIN_X, MARGIN_Y + 52,
          font=FONT_DISPLAY_XL, size=44, color=TEXT_HI)
    _text(c, a.ticker, PAGE_W - MARGIN_X, MARGIN_Y + 52,
          font=FONT_DISPLAY_XL, size=44, color=ORANGE, anchor="right")

    c.setStrokeColor(ORANGE)
    c.setLineWidth(1)
    c.line(MARGIN_X, _y(MARGIN_Y + 82), PAGE_W - MARGIN_X, _y(MARGIN_Y + 82))

    # ── LAYOUT 2 COLUMNAS ───────────────────────────────────────────────
    top_y = MARGIN_Y + 106
    avail_h = PAGE_H - top_y - MARGIN_Y - 30
    col_gap = 24
    col_w = (PAGE_W - 2 * MARGIN_X - col_gap) / 2

    # ════════ COLUMNA IZQUIERDA — FORTALEZAS + DEBILIDADES ═══════════════
    # Aplicamos el glosario plain-language SIN llamar a la API
    left_x = MARGIN_X
    strengths = [_simplify_lang(s) for s in (a.key_strengths or [])[:4]]
    weaknesses = [_simplify_lang(w) for w in (a.key_risks or [])[:4]]

    # Sección FORTALEZAS
    _text(c, "FORTALEZAS", left_x, top_y + 14,
          font=FONT_DISPLAY_XL, size=28, color=GREEN)
    _text(c, f"{len(strengths)} señales positivas detectadas",
          left_x, top_y + 42,
          font=FONT_REG, size=15, color=TEXT_LO)

    s_section_top = top_y + 62
    section_h = avail_h / 2 - 30  # mitad superior de la columna
    if strengths:
        card_gap_y = 12
        card_h = (section_h - card_gap_y * (len(strengths) - 1)) / max(len(strengths), 1)
        card_h = min(card_h, 88)  # max razonable

        for i, s in enumerate(strengths):
            cy_top = s_section_top + i * (card_h + card_gap_y)
            _box(c, left_x, cy_top, col_w, card_h, r=10,
                 fill=BG_CARD, stroke=GREEN, stroke_w=1)
            # Accent strip izquierdo
            c.setFillColor(GREEN)
            c.rect(left_x, _y(cy_top + card_h), 5, card_h, fill=1, stroke=0)
            # Check mark
            c.setFillColor(GREEN)
            c.circle(left_x + 30, _y(cy_top + card_h/2), 9, fill=1, stroke=0)
            _text(c, "✓", left_x + 30, cy_top + card_h/2 + 5,
                  font=FONT_BOLD, size=13, color=HexColor("#0A0D11"),
                  anchor="center")
            # texto
            _wrap(c, s, left_x + 64, cy_top + 28,
                  width=col_w - 84, font=FONT_REG, size=16,
                  color=TEXT_HI, line_height=1.35, max_lines=2)

    # Sección DEBILIDADES
    w_section_label_top = top_y + avail_h / 2 + 4
    _text(c, "DEBILIDADES", left_x, w_section_label_top + 14,
          font=FONT_DISPLAY_XL, size=28, color=RED)
    _text(c, f"{len(weaknesses)} riesgos a vigilar",
          left_x, w_section_label_top + 42,
          font=FONT_REG, size=15, color=TEXT_LO)

    w_section_top = w_section_label_top + 62
    if weaknesses:
        card_gap_y = 12
        card_h = (section_h - card_gap_y * (len(weaknesses) - 1)) / max(len(weaknesses), 1)
        card_h = min(card_h, 88)
        for i, w in enumerate(weaknesses):
            cy_top = w_section_top + i * (card_h + card_gap_y)
            _box(c, left_x, cy_top, col_w, card_h, r=10,
                 fill=BG_CARD, stroke=RED, stroke_w=1)
            c.setFillColor(RED)
            c.rect(left_x, _y(cy_top + card_h), 5, card_h, fill=1, stroke=0)
            c.setFillColor(RED)
            c.circle(left_x + 30, _y(cy_top + card_h/2), 9, fill=1, stroke=0)
            _text(c, "!", left_x + 30, cy_top + card_h/2 + 5,
                  font=FONT_BOLD, size=13, color=HexColor("#0A0D11"),
                  anchor="center")
            _wrap(c, w, left_x + 64, cy_top + 28,
                  width=col_w - 84, font=FONT_REG, size=16,
                  color=TEXT_HI, line_height=1.35, max_lines=2)

    # ════════ COLUMNA DERECHA — CHART PRECIOS + CTA BANNER ══════════════
    right_x = MARGIN_X + col_w + col_gap
    chart_h = avail_h * 0.50 - 12
    cta_top = top_y + chart_h + 24
    cta_h = avail_h - chart_h - 24

    # ── Chart de precios (top de la columna derecha) ──
    _box(c, right_x, top_y, col_w, chart_h, r=14,
         fill=BG_CARD, stroke=BORDER, stroke_w=1)
    _text(c, "RECORRIDO DEL PRECIO", right_x + 32, top_y + 42,
          font=FONT_DISPLAY_XL, size=26, color=TEXT_HI)
    _text(c, "Último año · líneas: mínimo · actual · potencial",
          right_x + 32, top_y + 70,
          font=FONT_REG, size=15, color=TEXT_LO)

    try:
        pc_fig = _build_price_journey_chart(a)
        if pc_fig is not None:
            inner_w = col_w - 24
            inner_h = chart_h - 90
            pc_png = _chart_png(pc_fig, width_px=1700,
                                height_px=int(inner_h * 1.5))
            if pc_png:
                c.drawImage(pc_png, right_x + 12,
                            _y(top_y + 84 + inner_h),
                            width=inner_w, height=inner_h,
                            preserveAspectRatio=True, mask='auto')
    except Exception:
        _text(c, "Chart de precios no disponible",
              right_x + col_w/2, top_y + chart_h/2,
              font=FONT_REG, size=14, color=TEXT_DIM, anchor="center")

    # ── CTA BANNER (sólido naranja, destaca al máximo) ──
    _box(c, right_x, cta_top, col_w, cta_h, r=16,
         fill=ORANGE, stroke=ORANGE_DK, stroke_w=3)

    # Headline grande en negro sobre naranja sólido
    _text(c, "¿QUIERES ANALIZAR ASÍ?",
          right_x + 36, cta_top + 56,
          font=FONT_DISPLAY_XL, size=36, color=HexColor("#0A0D11"))
    # El SUB se renderiza más abajo — después de que sepamos dónde
    # empieza el QR, para wrap el texto a la izquierda sin solaparlo.

    # ── Layout derecho del banner: LOGO grande (aspect original) + QR al lado ──
    # El logo conserva su forma rectangular original con esquinas redondeadas.
    # Se ubica en la columna derecha SIN reducir tamaño. El QR va a su IZQUIERDA.

    # Dimensiones disponibles
    # Cap del logo a 220pt — más allá de eso se come el ancho del sub
    logo_box_max = min(220, cta_h - 32)
    qr_s = 130  # QR fijo para dejar ancho al sub text grande

    # Logo box: bottom-right del banner
    logo_box_h = logo_box_max
    logo_box_w = logo_box_max  # box cuadrada, la imagen se ajustará con aspect
    logo_box_x = right_x + col_w - logo_box_w - 18
    logo_box_top = cta_top + 16

    if LOGO_PATH and LOGO_PATH.exists():
        styled_logo = _styled_logo_png(
            LOGO_PATH, max_dim_px=900,
            corner_radius_pct=0.12,
            glow_color=(255, 255, 200),
            glow_blur=36, glow_intensity=0.65,
            pad_px=70,
        )
        if styled_logo:
            # Drawimage con preserveAspectRatio dibuja la imagen dentro de
            # logo_box_w × logo_box_h manteniendo aspect del logo original.
            c.drawImage(styled_logo,
                        logo_box_x, _y(logo_box_top + logo_box_h),
                        width=logo_box_w, height=logo_box_h,
                        preserveAspectRatio=True, mask='auto')

    # QR a la IZQUIERDA del logo, centrado verticalmente
    qr_img = _qr_image(CLUB_DLP_URL, size_px=int(qr_s * 3))
    if qr_img is not None:
        qr_gap = 16
        qr_x_pos = logo_box_x - qr_gap - qr_s
        qr_top = cta_top + (cta_h - qr_s) / 2  # centrado vertical
        c.drawImage(qr_img, qr_x_pos, _y(qr_top + qr_s),
                    width=qr_s, height=qr_s, mask='auto')
        c.linkURL(CLUB_DLP_URL,
                  (qr_x_pos, _y(qr_top + qr_s),
                   qr_x_pos + qr_s, _y(qr_top)),
                  relative=0, thickness=0)
    else:
        qr_x_pos = logo_box_x  # sin QR, el btn puede crecer hasta logo

    # ── SUB-TEXTO ~3x el tamaño original (18→46pt) con wrap a la izquierda ──
    # Limitamos el ancho a sub_max_right para que NO invada el QR.
    sub_x = right_x + 36
    sub_max_right = qr_x_pos - 28
    sub_w = sub_max_right - sub_x
    _wrap(c, "Únete al Club DLP y usa esta misma IA para invertir mejor.",
          sub_x, cta_top + 108, width=sub_w,
          font=FONT_BOLD, size=38, color=HexColor("#0A0D11"),
          line_height=1.2, max_lines=4)

    # ── Botón CTA: ancho que NO invade el QR/logo ──
    btn_x = right_x + 36
    btn_max_right = qr_x_pos - 16 if qr_img is not None else logo_box_x - 16
    btn_w = btn_max_right - btn_x
    btn_w = min(btn_w, 420)
    btn_h = 64
    btn_top = cta_top + cta_h - btn_h - 28
    c.setFillColor(HexColor("#0A0D11"))
    c.setStrokeColor(HexColor("#0A0D11"))
    c.roundRect(btn_x, _y(btn_top + btn_h), btn_w, btn_h, 12, fill=1, stroke=0)
    _text(c, "ÚNETE AL CLUB DLP   →",
          btn_x + btn_w/2, btn_top + 38,
          font=FONT_DISPLAY_XL, size=20, color=ORANGE, anchor="center")
    _text(c, CLUB_DLP_URL, btn_x, btn_top + btn_h + 24,
          font=FONT_DISPLAY, size=13, color=HexColor("#0A0D11"))
    c.linkURL(CLUB_DLP_URL,
              (btn_x, _y(btn_top + btn_h), btn_x + btn_w, _y(btn_top)),
              relative=0, thickness=0)

    # Disclaimer
    _text(c, "Análisis educativo · No constituye recomendación de inversión · diariolargoplazo.com",
          PAGE_W/2, PAGE_H - 22,
          font=FONT_REG, size=9, color=TEXT_DIM, anchor="center")

