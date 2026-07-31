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

# ── Paleta — espejo EXACTO de los tokens de dashboard/styles.py ──────────
# El PDF se había quedado en la paleta neón anterior (naranja #FFB84D, verde
# #00FF88, texto #E4E7EC) mientras la app pasó al "terminal sobrio" de oro
# apagado. Al abrirlos juntos parecían dos productos distintos. Estos valores
# son ahora los MISMOS tokens que usan styles.py y charts.py, así que el PDF y
# la pantalla comparten identidad.
BG_DEEP    = HexColor("#0A0B0D")   # --bg
BG_CARD    = HexColor("#101216")   # --surface-1
BG_CARD2   = HexColor("#15181D")   # --surface-2
BG_CTA     = HexColor("#0D0F12")   # --surface-0
BG_PANEL   = HexColor("#07080B")   # PANEL_BG — fondo de las gráficas de score
ORANGE     = HexColor("#E2B25C")   # --accent (oro antiguo)
ORANGE_DK  = HexColor("#C08E3B")   # --accent-deep
GOLD       = HexColor("#F0C878")   # --accent-hi
GREEN      = HexColor("#3DD68C")   # --pos
GREEN_DK   = HexColor("#2FB374")
RED        = HexColor("#F1495F")   # --neg
RED_DK     = HexColor("#C93A4C")
BLUE       = HexColor("#6FA3E0")   # --info
BLUE_DK    = HexColor("#4E7CB0")
TEXT_HI    = HexColor("#F2F3F5")   # --text-hi
TEXT_MD    = HexColor("#C9CDD3")   # --text
TEXT_LO    = HexColor("#8D949E")   # --text-2
TEXT_DIM   = HexColor("#5E6570")   # --text-3
BORDER     = HexColor("#232830")   # --border-solid


# ── Sistema de tonos (calidad percibida) ─────────────────────────────────
# Los colores semánticos full-saturación (verde/rojo/oro puros) se ven
# chillones usados en bordes y números grandes. Estas variantes conservan
# la semántica pero con acabado premium:
#   _border_of → borde hair-line apagado (el color se insinúa, no grita)
#   _tint_of   → relleno de tarjeta con un tinte sutil del color
#   _num_of    → color de número grande: suavizado hacia blanco (pastel rico)
def _mix(c1: Color, c2: Color, t: float) -> Color:
    """Interpola linealmente entre dos colores. t=0 → c1, t=1 → c2."""
    return Color(
        c1.red + (c2.red - c1.red) * t,
        c1.green + (c2.green - c1.green) * t,
        c1.blue + (c2.blue - c1.blue) * t,
    )


def _border_of(color: Color) -> Color:
    return _mix(color, BG_DEEP, 0.55)


def _tint_of(color: Color) -> Color:
    return _mix(color, BG_CARD, 0.93)


def _num_of(color: Color) -> Color:
    return _mix(color, TEXT_HI, 0.22)

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


def _wrap_lines(c, txt, width, *, font=None, size=12, max_lines=None) -> list:
    """Solo calcula las líneas del wrap (sin dibujar). Para poder centrar."""
    if font is None:
        font = FONT_REG
    if not txt:
        return []
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
        while c.stringWidth(last + "…", font, size) > width and last:
            last = last[:-1]
        lines[-1] = last.rstrip() + "…"
    return lines


def _wrap_vcenter(c, txt, x, card_top, card_h, width, *, font=None, size=12,
                  color=TEXT_MD, line_height=1.35, max_lines=2):
    """Texto con wrap CENTRADO verticalmente dentro de una tarjeta de altura
    card_h. Evita el texto 'flotando arriba' en tarjetas altas."""
    if font is None:
        font = FONT_REG
    lines = _wrap_lines(c, txt, width, font=font, size=size, max_lines=max_lines)
    if not lines:
        return
    lh = size * line_height
    block_h = lh * (len(lines) - 1) + size
    cy = card_top + (card_h - block_h) / 2 + size * 0.82  # baseline 1ª línea
    c.setFont(font, size)
    c.setFillColor(color)
    for ln in lines:
        c.drawString(x, _y(cy), ln)
        cy += lh


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


# ── Traducción de VALORES de métricas (inglés → español, sin API) ────────
# El análisis guarda muchos valores categóricos en inglés (wide, risk-on,
# improving, Stage 2…). Aquí los pasamos a español simple para el PDF.
_VALUE_EXACT = {
    # moat / futuro
    "wide": "amplia", "narrow": "limitada", "none": "sin ventaja",
    "low": "bajo", "medium": "medio", "high": "alto", "critical": "crítico",
    "excellent": "excelente", "good": "buena", "average": "promedio", "poor": "pobre",
    "platform": "plataforma", "saas": "suscripción", "marketplace": "mercado",
    "traditional": "tradicional", "commodity": "materia prima", "other": "otro",
    "expanding rapidly": "crece rápido", "expanding": "en expansión",
    "stable": "estable", "contracting": "encogiéndose",
    # macro
    "risk-on": "apetito riesgo", "neutral": "neutral", "risk-off": "aversión",
    "high negative": "alta (neg.)", "high positive": "alta (pos.)",
    "strong": "fuerte", "weak": "débil",
    "low <20": "bajo", "elevated 20-30": "moderado", "high >30": "alto",
    "normal": "normal", "flat": "plana", "inverted": "invertida",
    "favorable": "favorable", "unfavorable": "desfavorable",
    # sentimiento / institucional / catalizadores
    "very bullish": "muy positivo", "bullish": "positivo",
    "very bearish": "muy negativo", "bearish": "negativo",
    "improving": "mejorando", "deteriorating": "empeorando",
    "accumulating": "acumulando", "distributing": "distribuyendo",
    "turnaround": "recuperación", "defensivo": "defensivo",
    "buy the fear": "comprar miedo", "sell the hype": "vender euforia",
    "no signal": "sin señal",
    "expanding": "en expansión",
}
_VALUE_WORDS = [
    (r"\bStage\b", "Fase"), (r"\bstage\b", "fase"),
    (r"\bdel float\b", "del total"), (r"\bfloat\b", "flotante"),
    (r"\bYoY\b", "interanual"), (r"\bforward\b", "estimado"),
    (r"\btrailing\b", "histórico"), (r"\bhistogram\b", "histograma"),
    (r"\bbeats?\b", "aciertos"), (r"\bswing low\b", "mínimo reciente"),
    (r"\bbullish\b", "positivo"), (r"\bbearish\b", "negativo"),
    (r"\bcontracting\b", "en descenso"), (r"\bexpanding\b", "en aumento"),
]


def _es_value(v, default="—"):
    """Traduce un valor de métrica a español simple. Tolerante a None/strings."""
    if v in (None, "", "N/A", "—"):
        return default
    import re as _re_v
    s = str(v).strip()
    low = s.lower()
    if low in _VALUE_EXACT:
        return _VALUE_EXACT[low]
    out = s
    for pat, rep in _VALUE_WORDS:
        out = _re_v.sub(pat, rep, out)
    return out


# ── Sectores (inglés de la fuente de datos → español) ───────────────────
_SECTOR_ES = {
    "technology": "Tecnología",
    "healthcare": "Salud",
    "financial services": "Servicios financieros",
    "consumer cyclical": "Consumo cíclico",
    "consumer defensive": "Consumo defensivo",
    "communication services": "Comunicaciones",
    "industrials": "Industria",
    "energy": "Energía",
    "real estate": "Bienes raíces",
    "utilities": "Servicios públicos",
    "basic materials": "Materiales básicos",
}


def _es_sector(s):
    if not s:
        return "—"
    return _SECTOR_ES.get(str(s).strip().lower(), str(s))


# ── Conclusiones simples por dimensión (cero narración de datos) ─────────
def _tier(score):
    s = _to_float(score, default=50.0)
    return "alto" if s >= 62 else "medio" if s >= 45 else "bajo"


_CONCLUSIONS = {
    "fundamentals": {
        "alto": "La empresa gana dinero de forma sólida y constante. Sus finanzas son sanas.",
        "medio": "La empresa es rentable, pero tiene algún punto financiero por mejorar.",
        "bajo": "Sus finanzas muestran debilidades: la rentabilidad o la deuda preocupan.",
    },
    "technical": {
        "alto": "El precio viene subiendo de forma sostenida. La tendencia la acompaña.",
        "medio": "El precio se mueve de lado, sin una dirección clara por ahora.",
        "bajo": "El precio viene débil o de bajada. Conviene esperar a que se estabilice.",
    },
    "future": {
        "alto": "Tiene una ventaja difícil de copiar y espacio para crecer por años.",
        "medio": "Es un negocio viable, pero su ventaja a largo plazo no es del todo clara.",
        "bajo": "Hay dudas reales sobre qué tan fuerte será este negocio en el futuro.",
    },
    "institutional": {
        "alto": "Los grandes inversores están comprando y respaldan la acción.",
        "medio": "Los grandes inversores están a la expectativa, sin un movimiento claro.",
        "bajo": "Por ahora hay poco respaldo de los grandes inversores.",
    },
    "catalysts": {
        "alto": "Tiene eventos cercanos (como resultados) que pueden impulsar el precio.",
        "medio": "Tiene algunos eventos por delante, pero sin un impulso claro inmediato.",
        "bajo": "No se ven eventos importantes que muevan el precio en el corto plazo.",
    },
    "macro": {
        "alto": "El entorno general del mercado juega a su favor.",
        "medio": "El entorno general del mercado está neutro para la empresa.",
        "bajo": "El entorno general del mercado juega en su contra ahora mismo.",
    },
    "sentiment": {
        "alto": "El ánimo y las noticias sobre la empresa son positivos.",
        "medio": "El ánimo del mercado sobre la empresa es neutral.",
        "bajo": "El ánimo y las noticias sobre la empresa son negativos.",
    },
    "risk": {
        "alto": "Lo que puede ganar supera con claridad a lo que puede perder.",
        "medio": "El posible premio y el posible riesgo están bastante parejos hoy.",
        "bajo": "Hoy se arriesga más de lo que se puede ganar. Mejor esperar un precio más bajo.",
    },
}


def _conclusion(rkey, score):
    """Conclusión simple en español para una dimensión, según su puntaje."""
    table = _CONCLUSIONS.get(rkey)
    if not table:
        return ""
    return table[_tier(score)]


def _score_tag(score):
    """Etiqueta corta del resultado, en español."""
    s = _to_float(score, default=50.0)
    if s >= 70: return "Resultado: muy bueno"
    if s >= 55: return "Resultado: bueno"
    if s >= 45: return "Resultado: regular"
    return "Resultado: débil"


# ── Fortalezas y debilidades automáticas (conclusiones, no datos) ───────
_SW_TEXT = {
    "fundamentals": ("Finanzas sólidas: gana dinero de forma constante y sin depender de deuda.",
                     "Finanzas flojas: su rentabilidad o su deuda son un punto débil."),
    "future":       ("Buen futuro: tiene una ventaja difícil de copiar y espacio para crecer.",
                     "Futuro incierto: su ventaja competitiva no es clara."),
    "technical":    ("El precio acompaña: viene en una tendencia positiva.",
                     "El precio no acompaña: viene débil o de bajada."),
    "institutional":("Los grandes inversores respaldan la acción.",
                     "Poco respaldo de los grandes inversores por ahora."),
    "catalysts":    ("Tiene eventos cercanos que pueden impulsar el precio.",
                     "Le faltan eventos claros que impulsen el precio pronto."),
    "macro":        ("El entorno general del mercado la acompaña.",
                     "El entorno general del mercado juega en su contra."),
    "sentiment":    ("El ánimo del mercado hacia la empresa es positivo.",
                     "El ánimo del mercado hacia la empresa es negativo."),
    "risk":         ("Buena relación entre lo que puede ganar y lo que puede perder.",
                     "Hoy se arriesga más de lo que se puede ganar: mejor esperar mejor precio."),
}


def _auto_strengths_weaknesses(a):
    """Genera fortalezas y debilidades como conclusiones simples en español,
    a partir de los puntajes de cada dimensión (no narra los datos crudos)."""
    sb = a.score_breakdown or {}
    dims = [(k, _to_float(sb.get(k), default=50.0)) for k in _SW_TEXT.keys()]

    strengths = [_SW_TEXT[k][0] for k, s in sorted(dims, key=lambda kv: kv[1], reverse=True) if s >= 60]
    weaknesses = [_SW_TEXT[k][1] for k, s in sorted(dims, key=lambda kv: kv[1]) if s <= 50]

    # Debilidad extra por valoración cara (concreta y fácil de entender)
    fund = (a.reports or {}).get("fundamentals")
    pe = _to_float((fund.key_metrics or {}).get("pe_ratio")) if fund else None
    if pe is not None and pe > 28:
        weaknesses.insert(0, "La acción no está barata hoy: pagas bastante por lo que la empresa gana.")

    # Garantizar al menos 2 de cada uno (si faltan, usar extremos)
    if len(strengths) < 2:
        for k, s in sorted(dims, key=lambda kv: kv[1], reverse=True):
            t = _SW_TEXT[k][0]
            if t not in strengths:
                strengths.append(t)
            if len(strengths) >= 2:
                break
    if len(weaknesses) < 2:
        for k, s in sorted(dims, key=lambda kv: kv[1]):
            t = _SW_TEXT[k][1]
            if t not in weaknesses:
                weaknesses.append(t)
            if len(weaknesses) >= 2:
                break

    return strengths[:4], weaknesses[:4]


def _alpha_simple(a):
    """Frase breve y simple para el hero, según la recomendación."""
    rec = (a.recommendation or "").upper()
    if rec in ("MUY ATRACTIVO", "STRONG BUY"):
        return "Oportunidad atractiva: la calidad del negocio y el precio acompañan."
    if rec in ("ATRACTIVO", "BUY"):
        return "Buena empresa con un punto de entrada razonable."
    if rec in ("EVITAR", "PASS"):
        return "Por ahora no luce como oportunidad. Mejor esperar."
    return "Buena empresa; conviene esperar un mejor precio de entrada."


def _horizon_simple(a):
    """Horizonte en lenguaje simple."""
    return "Pensado para el largo plazo (años)"


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


def _chart_png_fiel(fig, width_px: int, height_px: int, scale: int = 5) -> Optional[ImageReader]:
    """Rasteriza una figura TAL COMO SE VE EN LA APP, solo a más resolución.

    La diferencia con _chart_png es sutil pero decisiva: aquí se usa el tamaño
    LÓGICO real del componente (≈500px) y se sube el `scale`, en vez de estirar
    el lienzo a 2000px lógicos. Plotly dimensiona las fuentes en puntos sobre el
    lienzo lógico, así que un lienzo enorme hace que una fuente de tamaño 11
    —la que usa la app— salga como una mota. Con `scale` todo crece en
    proporción: mismo diseño, misma identidad, cuatro veces más nítido.
    """
    try:
        png_bytes = fig.to_image(format="png", width=width_px, height=height_px,
                                 scale=scale, engine="kaleido")
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
        img = qr.make_image(fill_color="#E2B25C", back_color="#0D0F12")
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
         r=14, fill=BG_CARD, stroke=_border_of(ORANGE), stroke_w=1)

    # Brand top-right
    _text(c, "◈  ANALIZADOR DLP", PAGE_W - MARGIN_X - 28, hero_top + 26,
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

    sub = f"{_es_sector(a.sector)}   ·   {_horizon_simple(a)}"
    left_w = right_zone_x - tx - 30
    _wrap(c, sub, tx, hero_top + 204, width=left_w,
          font=FONT_REG, size=16, color=TEXT_LO,
          line_height=1.3, max_lines=1)

    # Conclusión breve y simple (en español, generada por código)
    alpha_brief = _alpha_simple(a)
    if alpha_brief:
        _wrap(c, alpha_brief, tx, hero_top + 230, width=left_w,
              font=FONT_REG, size=14, color=GOLD,
              line_height=1.3, max_lines=1)

    # Composite score (right side) — número en tono premium, no neón
    sc_f = _to_float(a.composite_score)
    sc_color = _score_color(sc_f if sc_f is not None else 50)
    _text(c, f"{sc_f:.1f}" if sc_f is not None else "—",
          PAGE_W - MARGIN_X - 60, hero_top + 130,
          font=FONT_DISPLAY_XL, size=84, color=_num_of(sc_color), anchor="right")
    _text(c, "PUNTAJE GLOBAL  /  100", PAGE_W - MARGIN_X - 60, hero_top + 168,
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
    # mid_h reducido (500→430) para dar espacio a la franja de TESIS abajo.
    mid_top = hero_top + hero_h + 22
    mid_h = 430
    gap_card = 18
    panel_w = (PAGE_W - 2 * MARGIN_X - gap_card * 2) / 3  # ≈ 581pt

    # ── PANEL 1 — GAUGE (DLP SCORE) ──
    p1_x = MARGIN_X
    _box(c, p1_x, mid_top, panel_w, mid_h, r=12,
         fill=BG_CARD, stroke=BORDER, stroke_w=1)
    _text(c, "PUNTAJE DLP", p1_x + 28, mid_top + 38,
          font=FONT_DISPLAY, size=19, color=TEXT_LO)
    _text(c, rec.upper(), p1_x + 28, mid_top + 64,
          font=FONT_DISPLAY, size=14, color=fill_c)

    try:
        from dashboard.charts import build_gauge
        # Figura de la app SIN retoques: el tacómetro actual ya trae el arco con
        # gradiente térmico, el número grande y la paleta oro. Los overrides que
        # había aquí (paper_bgcolor #141920, tickfont #7A8898, barra #FFB84D)
        # eran de la paleta ANTERIOR y desalineaban el PDF de la app.
        g_fig = build_gauge(sc_f if sc_f is not None else 50, rec)
        g_png = _chart_png_fiel(g_fig, width_px=520, height_px=440, scale=6)
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
        # Se usa la figura de la app TAL CUAL. Antes aquí se reescribían los
        # theta, el rango del eje, las fuentes y toda la paleta, y eso es lo que
        # rompía el radar: el snowflake actual dibuja sus etiquetas como una
        # TRAZA DE TEXTO a r=23.2 sobre un eje que llega a 28, así que al
        # forzar range=[0,20] las etiquetas quedaban FUERA del área y
        # desaparecían; además se pisaba la paleta nueva con la vieja.
        sf_fig = build_snowflake(a.snowflake or {})
        sf_png = _chart_png_fiel(sf_fig, width_px=520, height_px=460, scale=6)
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
    _text(c, "8 ANÁLISIS · 0–100 c/u", p3_x + 28, mid_top + 64,
          font=FONT_REG, size=14, color=TEXT_DIM)

    try:
        from dashboard.charts import build_score_breakdown
        # Figura de la app SIN retoques de paleta ni de ejes: el desglose actual
        # ya trae los códigos dorados (FN/TC/FU/SM/CT/MC/SN/RS), las barras con
        # esquinas redondeadas, el riel de fondo 0-100 y los VALORES A LA
        # DERECHA. Lo único que se mantiene es traducir "Smart Money".
        # Se reconstruye desde los REPORTES reales (igual que hace el Overview de
        # la app): el score_breakdown que devuelve el modelo puede desviarse del
        # puntaje que realmente sacó cada agente, y entonces el PDF y la pantalla
        # mostraban cifras distintas para el mismo análisis.
        _bd = dict(a.score_breakdown or {})
        for _k in ("fundamentals", "technical", "future", "institutional",
                   "catalysts", "macro", "sentiment", "risk"):
            _rep = (a.reports or {}).get(_k)
            if _rep is not None and getattr(_rep, "score", None) is not None:
                _bd[_k] = _rep.score
        sb_fig = build_score_breakdown(_bd)
        for _tr in sb_fig.data:
            if getattr(_tr, "y", None):
                _tr.y = [str(_yy).replace("Smart Money", "Institucional") for _yy in _tr.y]
        sb_png = _chart_png_fiel(sb_fig, width_px=560, height_px=460, scale=6)
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
            ("Institucional", sb.get("institutional",50)),
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

    # ── FRANJA DE TESIS — la teoría en palabras claras ──────────────────
    # Lo que faltaba: ANTES el PDF era solo datos; esta franja explica en
    # 2-3 líneas simples POR QUÉ la acción tiene el veredicto que tiene.
    thesis_top = mid_top + mid_h + 18
    thesis_h = 96
    _box(c, MARGIN_X, thesis_top, PAGE_W - 2*MARGIN_X, thesis_h, r=12,
         fill=BG_CARD, stroke=_border_of(ORANGE), stroke_w=1)
    c.setFillColor(ORANGE)
    c.rect(MARGIN_X, _y(thesis_top + thesis_h), 4, thesis_h, fill=1, stroke=0)
    _text(c, "LA TESIS EN CORTO", MARGIN_X + 28, thesis_top + 30,
          font=FONT_DISPLAY, size=14, color=ORANGE)
    thesis_txt = _truncate_by_sentence(
        _simplify_lang(a.investment_thesis or ""), 330)
    if not thesis_txt or len(thesis_txt) < 40:
        thesis_txt = _alpha_simple(a) or (
            "Puntaje global de "
            + (f"{sc_f:.0f}" if sc_f is not None else "—")
            + "/100. Revisa las fortalezas y debilidades de la última página "
              "para entender qué pesa a favor y qué pesa en contra.")
    _wrap(c, thesis_txt, MARGIN_X + 28, thesis_top + 56,
          width=PAGE_W - 2*MARGIN_X - 56,
          font=FONT_REG, size=16, color=TEXT_MD,
          line_height=1.35, max_lines=2)

    # ── FOOTER: 3 TILES DE PRECIO (rediseñados: tinte sutil, no neón) ───
    foot_top = thesis_top + thesis_h + 18
    foot_h = 148

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

    stop_sub = (f"riesgo estimado: −{abs(risk_pct):.1f}%" if risk_pct
                else "piso estimado si sale mal")
    tgt_sub  = (f"recorrido posible: +{reward_pct:.1f}%" if reward_pct
                else "objetivo si la tesis se cumple")

    # SOLO 3 tiles: Precio Actual / Precio Mínimo / Precio Potencial
    # Sin R/R, sin Sizing, sin terminología de trading.
    tiles = [
        ("PRECIO ACTUAL",     fmt_money(a.entry_price),  ORANGE, "lo que cuesta hoy · último cierre"),
        ("PRECIO MÍNIMO",     fmt_money(a.stop_loss),    RED,    stop_sub),
        ("PRECIO POTENCIAL",  fmt_money(a.target_price), GREEN,  tgt_sub),
    ]
    gap = 24
    total_w = PAGE_W - 2 * MARGIN_X
    tw = (total_w - gap * 2) / 3
    for i, (label, value, color, sub) in enumerate(tiles):
        x = MARGIN_X + i * (tw + gap)
        # Tinte sutil + borde apagado (antes: borde a color pleno, chillón)
        _box(c, x, foot_top, tw, foot_h, r=12,
             fill=_tint_of(color), stroke=_border_of(color), stroke_w=1)
        # Acento superior fino — único toque de color pleno
        c.setFillColor(color)
        c.rect(x, _y(foot_top + 4), tw, 4, fill=1, stroke=0)
        # Punto indicador + label
        c.setFillColor(color)
        c.circle(x + tw/2 - c.stringWidth(label, FONT_DISPLAY, 17)/2 - 16,
                 _y(foot_top + 40), 5, fill=1, stroke=0)
        _text(c, label, x + tw/2, foot_top + 46,
              font=FONT_DISPLAY, size=17, color=TEXT_LO, anchor="center")
        # Número en tono premium (suavizado, no neón)
        _text(c, value, x + tw/2, foot_top + 98,
              font=FONT_DISPLAY_XL, size=44, color=_num_of(color), anchor="center")
        if sub:
            _text(c, sub, x + tw/2, foot_top + 128,
                  font=FONT_REG, size=14, color=TEXT_LO, anchor="center")

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
    if "3" in stage: return "Distribución — el impulso se agota", ORANGE
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

    # Glow sutil (una sola capa tenue — antes había 2 capas gruesas que se
    # veían como un halo pesado poco elegante).
    # Paleta = tokens de la app (oro #E2B25C): antes iba hardcodeada la paleta
    # neón vieja (#FFB84D) y la alineación global de constantes no llegaba aquí.
    fig.add_trace(go.Scatter(
        x=dates, y=prices,
        mode="lines",
        line=dict(color="rgba(226,178,92,0.14)", width=11,
                  shape="spline", smoothing=0.5),
        hoverinfo="skip", showlegend=False,
    ))
    # Línea principal + fill gradient debajo
    fig.add_trace(go.Scatter(
        x=dates, y=prices,
        mode="lines",
        line=dict(color="#E2B25C", width=3.5,
                  shape="spline", smoothing=0.5),
        fill="tozeroy",
        fillcolor="rgba(226,178,92,0.08)",
        hoverinfo="skip", showlegend=False,
    ))
    # Marker del precio actual (punto vivo discreto)
    fig.add_trace(go.Scatter(
        x=[dates[-1]], y=[prices[-1]],
        mode="markers",
        marker=dict(size=16, color="#F0C878",
                    line=dict(width=3, color="white")),
        hoverinfo="skip", showlegend=False,
    ))

    min_p, max_p = min(prices), max(prices)
    pad = (max_p - min_p) * 0.12
    fig.update_layout(
        paper_bgcolor="#101216", plot_bgcolor="#101216",
        margin=dict(l=110, r=80, t=50, b=60),
        font=dict(family="Helvetica", color="#C9CDD3", size=24),
        xaxis=dict(
            showgrid=False, showline=False,
            tickfont=dict(size=20, color="#8D949E"),
            tickformat="%b %Y", nticks=6,
        ),
        yaxis=dict(
            showgrid=True, gridcolor="rgba(255,255,255,0.06)", gridwidth=1,
            tickfont=dict(size=20, color="#8D949E"),
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
          color=_num_of(_score_color(sc_f if sc_f is not None else 50)),
          anchor="right")

    c.setStrokeColor(_border_of(ORANGE))
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

    # Score grande arriba a la derecha (tono premium)
    _text(c, f"{fund_score:.0f}", fx + col_w - 32, top_y + 60,
          font=FONT_DISPLAY_XL, size=58, color=_num_of(fund_color), anchor="right")
    _text(c, "DE 100", fx + col_w - 32, top_y + 92,
          font=FONT_DISPLAY, size=14, color=TEXT_LO, anchor="right")

    # Veredicto en banda destacada (tinte sutil, borde apagado)
    verdict_text, verdict_col = _verdict_stability(fund_score)
    vb_top = top_y + 120
    vb_h = 66
    _box(c, fx + 24, vb_top, col_w - 48, vb_h, r=10,
         fill=_tint_of(verdict_col), stroke=_border_of(verdict_col), stroke_w=1)
    c.setFillColor(verdict_col)
    c.circle(fx + 54, _y(vb_top + vb_h/2), 7, fill=1, stroke=0)
    _text(c, verdict_text, fx + 76, vb_top + vb_h/2 + 7,
          font=FONT_DISPLAY, size=22, color=_num_of(verdict_col))

    # Teoría en una línea: qué estás viendo en este panel
    _wrap(c, "Los fundamentales miden la salud del negocio: cuánto crece, "
             "cuánto gana de verdad y cuánto debe. Es la base de todo.",
          fx + 26, vb_top + vb_h + 26, width=col_w - 52,
          font=FONT_REG, size=14, color=TEXT_LO, line_height=1.3, max_lines=2)

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
                s = _es_value(s)
                # Estos KPIs son numéricos: quedarnos solo con el número + unidad
                # (ej "16.6% interanual" → "16.6%"); la etiqueta ya da el contexto.
                import re as _re_kml
                mnum = _re_kml.match(r"[~+\-]?\$?\d[\d.,]*\s*[%x]?", s)
                if mnum and mnum.group(0).strip():
                    s = mnum.group(0).strip()
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

    m_top = vb_top + vb_h + 62   # deja sitio a la línea de teoría
    m_gap_x = 18
    m_gap_y = 14
    m_cols = 2
    m_rows = 3
    m_card_w = (col_w - 48 - m_gap_x) / m_cols
    m_card_h = (avail_h - (vb_top - top_y) - vb_h - 82 - m_gap_y * (m_rows - 1)) / m_rows

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
          font=FONT_DISPLAY_XL, size=58, color=_num_of(tech_color), anchor="right")
    _text(c, "DE 100", tx_x + col_w - 32, top_y + 92,
          font=FONT_DISPLAY, size=14, color=TEXT_LO, anchor="right")

    # Veredicto técnico (tinte sutil, borde apagado)
    stage_val = (tech_rpt.key_metrics or {}).get("stage", "") if tech_rpt else ""
    vt_text, vt_col = _verdict_trend(tech_score, stage_val)
    vtb_top = top_y + 120
    vtb_h = 66
    _box(c, tx_x + 24, vtb_top, col_w - 48, vtb_h, r=10,
         fill=_tint_of(vt_col), stroke=_border_of(vt_col), stroke_w=1)
    c.setFillColor(vt_col)
    c.circle(tx_x + 54, _y(vtb_top + vtb_h/2), 7, fill=1, stroke=0)
    _text(c, vt_text, tx_x + 76, vtb_top + vtb_h/2 + 7,
          font=FONT_DISPLAY, size=22, color=_num_of(vt_col))

    # Teoría en una línea: qué mide (y qué NO mide) la tendencia
    _wrap(c, "La tendencia dice cómo se mueve el precio y su momento — no si "
             "el negocio es bueno. Sirve para elegir CUÁNDO, no QUÉ.",
          tx_x + 26, vtb_top + vtb_h + 26, width=col_w - 52,
          font=FONT_REG, size=14, color=TEXT_LO, line_height=1.3, max_lines=2)

    # Chart de línea
    chart_top = vtb_top + vtb_h + 58
    chart_h = avail_h - (vtb_top - top_y) - vtb_h - 136
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
          color=_num_of(_score_color(sc_f if sc_f is not None else 50)),
          anchor="right")

    c.setStrokeColor(_border_of(ORANGE))
    c.setLineWidth(1)
    c.line(MARGIN_X, _y(MARGIN_Y + 108), PAGE_W - MARGIN_X, _y(MARGIN_Y + 108))

    # ── SCOREBOARD HORIZONTAL (8 pills, mucho más legible que un bar chart) ──
    sb_top = MARGIN_Y + 126
    sb_h = 120
    _box(c, MARGIN_X, sb_top, PAGE_W - 2*MARGIN_X, sb_h, r=12,
         fill=BG_CARD, stroke=BORDER, stroke_w=1)
    _text(c, "PUNTAJES  ·  8 DIMENSIONES",
          MARGIN_X + 32, sb_top + 34,
          font=FONT_DISPLAY, size=17, color=ORANGE)
    # Cómo leer los colores — teoría en una línea
    _text(c, "cada dimensión va de 0 a 100  ·  verde = a favor  ·  ámbar = neutral  ·  rojo = en contra",
          PAGE_W - MARGIN_X - 32, sb_top + 34,
          font=FONT_REG, size=13, color=TEXT_LO, anchor="right")

    # 8 pills colocadas horizontalmente, color por score
    sb = a.score_breakdown or {}
    score_pills = [
        ("Fundamentales", sb.get("fundamentals", 50)),
        ("Técnico",       sb.get("technical",    50)),
        ("Futuro",        sb.get("future",       50)),
        ("Institucional", sb.get("institutional",50)),
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
        # Pill body — tinte sutil + borde apagado (antes: borde neón 1.5w)
        _box(c, px, pill_y_top, pill_w, pill_h, r=8,
             fill=_tint_of(col), stroke=_border_of(col), stroke_w=1)
        # Accent left bar
        c.setFillColor(col)
        c.rect(px, _y(pill_y_top + pill_h), 4, pill_h, fill=1, stroke=0)
        # Score grande en tono premium
        _text(c, f"{s:.0f}", px + 16, pill_y_top + 40,
              font=FONT_DISPLAY_XL, size=30, color=_num_of(col))
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
                # Quedarse con la primera parte si trae '/' o '(' (valores compuestos)
                if "/" in s and len(s) > 14:
                    s = s.split("/")[0].strip()
                if "(" in s:
                    s = s.split("(")[0].strip()
                # Traducir el valor a español simple (wide→amplia, risk-on→…)
                s = _es_value(s)
                # Hard-cap de longitud para que quepa en la card
                if len(s) > 16:
                    s = s[:15].rstrip(",;: ") + "…"
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
         "VALORACIÓN", km(reports.get("fundamentals"), "forward_pe", "pe_forward", "pe_ratio"),
         "RENT. CAPITAL", km(reports.get("fundamentals"), "roic", "roic_pct", "roe")),
        ("TÉCNICO",         "▲", "technical",
         "FASE",    km(reports.get("technical"), "stage", "stage_minervini", "minervini_stage"),
         "FUERZA",  km(reports.get("technical"), "rsi", "rsi_14")),
        ("FUTURO",          "◇", "future",
         "VENTAJA", km(reports.get("future"), "moat_strength", "moat", "moat_quality"),
         "DISRUPCIÓN", km(reports.get("future"), "disruption_risk", "disruption")),
        ("INSTITUCIONAL",   "⬢", "institutional",
         "PROPIEDAD", km(reports.get("institutional"), "institutional_ownership", "inst_ownership_pct", "ownership"),
         "DIRECTIVOS", km(reports.get("institutional"), "insider_buying_signal", "insider_signal", "smart_money_signal")),
        ("CATALIZADORES",   "✦", "catalysts",
         "PRÓX. RESULT.", km(reports.get("catalysts"), "next_earnings", "next_earnings_days", "days_to_earnings"),
         "ACIERTOS", km(reports.get("catalysts"), "beat_rate", "earnings_beat_rate")),
        ("MACRO Y SECTOR",  "⊕", "macro",
         "ENTORNO", km(reports.get("macro"), "market_environment", "market_env", "regime"),
         "SECTOR",  km(reports.get("macro"), "sector_momentum", "sector_perf", "sector")),
        ("SENTIMIENTO",     "◐", "sentiment",
         "NARRATIVA", km(reports.get("sentiment"), "narrative", "dominant_theme", "narrative_theme"),
         "TENDENCIA", km(reports.get("sentiment"), "sentiment_momentum", "sentiment_trend", "momentum")),
        ("RIESGO",          "◈", "risk",
         "GANA/PIERDE", _extract_ratio(a.risk_reward),
         "TAMAÑO", (lambda f: f"{f:.1f}%" if f is not None else "—")(_to_float(a.position_size_pct))),
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
              font=FONT_BOLD, size=26, color=_num_of(sc_color))
        _text(c, title, cx + 54, ctop + 40,
              font=FONT_DISPLAY, size=20, color=TEXT_HI)
        _text(c, f"{score:.0f}", cx + card_w - 24, ctop + 42,
              font=FONT_DISPLAY_XL, size=32, color=_num_of(sc_color), anchor="right")
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

        # ── CONCLUSIÓN SIMPLE (en español, generada por código) ──
        insight = _conclusion(rkey, score)
        if insight:
            _text(c, "“", cx + 22, ctop + 176,
                  font=FONT_DISPLAY_XL, size=38, color=ORANGE)
            _wrap(c, insight, cx + 54, ctop + 168,
                  width=card_w - 76, font=FONT_REG, size=18,
                  color=TEXT_MD, line_height=1.4, max_lines=4)

        # ── ETIQUETA DE RESULTADO al pie ──
        pro = _score_tag(score)
        if pro:
            pro_y = ctop + card_h - 26
            c.setFillColor(sc_color)
            c.circle(cx + 26, _y(pro_y - 5), 5, fill=1, stroke=0)
            _wrap(c, pro, cx + 42, pro_y,
                  width=card_w - 62, font=FONT_REG, size=14,
                  color=TEXT_LO, line_height=1.3, max_lines=1)

    # Footer disclaimer
    _text(c, "Análisis educativo · Lenguaje de inversión a largo plazo · No constituye recomendación",
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
    # Paleta = tokens de la app (oro #E2B25C / verde #3DD68C / rojo #F1495F).
    # Antes iba hardcodeada la paleta neón vieja (#FFB84D/#00FF88/#FF3B5C) y la
    # alineación global de constantes no llegaba aquí.
    fig.add_trace(go.Scatter(x=dates, y=prices, mode="lines",
        line=dict(color="rgba(226,178,92,0.14)", width=11, shape="spline", smoothing=0.5),
        hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(x=dates, y=prices, mode="lines",
        line=dict(color="rgba(226,178,92,0.0)", width=1, shape="spline", smoothing=0.5),
        hoverinfo="skip", showlegend=False))
    fig.add_trace(go.Scatter(x=dates, y=prices, mode="lines",
        line=dict(color="#E2B25C", width=3.5, shape="spline", smoothing=0.5),
        fill="tozeroy", fillcolor="rgba(226,178,92,0.08)",
        hoverinfo="skip", showlegend=False))
    # Marker del precio actual
    fig.add_trace(go.Scatter(x=[dates[-1]], y=[prices[-1]], mode="markers",
        marker=dict(size=16, color="#F0C878", line=dict(width=3, color="white")),
        hoverinfo="skip", showlegend=False))

    # El rango del eje se calcula ANTES de colocar las etiquetas: el algoritmo
    # anti-colisión necesita saber cuánto mide una "altura de etiqueta" en
    # unidades de precio.
    all_pts = prices + [v for v in (cur_f, min_f, pot_f) if v is not None]
    min_p, max_p = min(all_pts), max(all_pts)
    pad = (max_p - min_p) * 0.08
    y_lo = max(0, min_p - pad)
    y_hi = max_p + pad
    y_span = (y_hi - y_lo) or 1.0

    # ── Líneas horizontales + etiquetas SIN SOLAPES ─────────────────────────
    # La línea punteada se queda SIEMPRE en su precio real. Lo que se separa es
    # la ETIQUETA: si dos precios caen cerca (típico: Actual y Mínimo con un
    # stop del −5%), las cajas de texto de dos líneas se pisaban una a otra.
    # Algoritmo: ordenar por precio y aplicar una pasada hacia arriba que impone
    # una separación mínima, luego reencajar el grupo dentro del eje si el
    # empuje lo sacó. La separación es el 20% del rango: medido en el PDF real,
    # una etiqueta de DOS líneas a size 20 ocupa ~14.5% del eje (la figura se
    # rasteriza a ~510px con ~410px de área útil), así que 15% dejaba las cajas
    # BESÁNDOSE (visto con PEP: Actual $137 / Mínimo $131). Con 20% queda un
    # hueco real de ~22px incluso en el peor caso de tres etiquetas seguidas.
    niveles = [(v, nombre, color, dash) for v, nombre, color, dash in (
        (min_f, "Mínimo",    "#F1495F", "dash"),
        (cur_f, "Actual",    "#E2B25C", "dot"),
        (pot_f, "Potencial", "#3DD68C", "dash"),
    ) if v is not None]
    niveles.sort(key=lambda n: n[0])

    MIN_SEP = y_span * 0.20
    label_y = [n[0] for n in niveles]
    for i in range(1, len(label_y)):
        if label_y[i] - label_y[i - 1] < MIN_SEP:
            label_y[i] = label_y[i - 1] + MIN_SEP
    # Si el empuje sacó la última etiqueta por arriba, bajar el grupo entero y
    # re-imponer la separación desde abajo (sin dejar que caiga bajo el eje).
    exceso = label_y[-1] - (y_hi - MIN_SEP * 0.35)
    if exceso > 0:
        label_y = [y - exceso for y in label_y]
        label_y[0] = max(label_y[0], y_lo + MIN_SEP * 0.35)
        for i in range(1, len(label_y)):
            if label_y[i] - label_y[i - 1] < MIN_SEP:
                label_y[i] = label_y[i - 1] + MIN_SEP

    shapes = []
    annotations = []
    last_date = dates[-1]
    for (valor, nombre, color, dash), y_lbl in zip(niveles, label_y):
        shapes.append(dict(type="line", x0=dates[0], x1=last_date,
                           y0=valor, y1=valor, xref="x", yref="y",
                           line=dict(color=color, width=2, dash=dash)))
        annotations.append(dict(x=1, xref="paper", y=y_lbl, yref="y",
                                xanchor="left", yanchor="middle",
                                text=f"  <b>{nombre}</b><br>  ${valor:,.0f}",
                                showarrow=False,
                                font=dict(size=20, color=color,
                                          family="Helvetica-Bold")))

    fig.update_layout(
        paper_bgcolor="#101216", plot_bgcolor="#101216",
        margin=dict(l=110, r=200, t=40, b=60),
        font=dict(family="Helvetica", color="#C9CDD3", size=22),
        xaxis=dict(showgrid=False, showline=False,
                   tickfont=dict(size=20, color="#8D949E"),
                   tickformat="%b %Y", nticks=6),
        yaxis=dict(showgrid=True, gridcolor="rgba(255,255,255,0.06)",
                   tickfont=dict(size=20, color="#8D949E"),
                   tickprefix="$",
                   range=[y_lo, y_hi]),
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
    # Cómo leer esta página — teoría en una línea
    _text(c, "Lo que pesa a favor, lo que pesa en contra, y el recorrido del precio en el último año.",
          MARGIN_X, MARGIN_Y + 76,
          font=FONT_REG, size=14, color=TEXT_LO)

    c.setStrokeColor(_border_of(ORANGE))
    c.setLineWidth(1)
    c.line(MARGIN_X, _y(MARGIN_Y + 88), PAGE_W - MARGIN_X, _y(MARGIN_Y + 88))

    # ── LAYOUT 2 COLUMNAS ───────────────────────────────────────────────
    top_y = MARGIN_Y + 112
    avail_h = PAGE_H - top_y - MARGIN_Y - 30
    col_gap = 24
    col_w = (PAGE_W - 2 * MARGIN_X - col_gap) / 2

    # ════════ COLUMNA IZQUIERDA — FORTALEZAS + DEBILIDADES ═══════════════
    # Conclusiones simples en español generadas por código (no narran datos
    # ni dejan términos en inglés). Derivadas de los puntajes de cada dimensión.
    #
    # LAYOUT DINÁMICO: antes "DEBILIDADES" se pintaba a mitad fija de la
    # columna y, con 4+ fortalezas, las tarjetas la PISABAN (solapamiento).
    # Ahora la altura de tarjeta se calcula con el total de ítems de AMBAS
    # secciones y cada bloque empieza exactamente donde terminó el anterior.
    left_x = MARGIN_X
    strengths, weaknesses = _auto_strengths_weaknesses(a)

    header_h = 54          # título + subtítulo compactos de cada sección
    section_gap = 26       # aire entre el fin de fortalezas y DEBILIDADES
    card_gap_y = 12
    n_s, n_w = len(strengths), len(weaknesses)
    total_cards = max(n_s + n_w, 1)
    gaps_h = card_gap_y * (max(n_s - 1, 0) + max(n_w - 1, 0))
    usable_h = avail_h - 2 * header_h - section_gap - gaps_h
    card_h = max(52.0, min(usable_h / total_cards, 84.0))

    def _verdict_section(title, subtitle, items, col, icon, start_top):
        """Dibuja header + tarjetas de una sección. Devuelve el top siguiente."""
        _text(c, title, left_x, start_top + 20,
              font=FONT_DISPLAY_XL, size=26, color=_num_of(col))
        _text(c, subtitle, left_x, start_top + 44,
              font=FONT_REG, size=14, color=TEXT_LO)
        cy_top = start_top + header_h + 8
        for it in items:
            # Tarjeta premium: tinte sutil del color + borde apagado
            _box(c, left_x, cy_top, col_w, card_h, r=10,
                 fill=_tint_of(col), stroke=_border_of(col), stroke_w=1)
            # Acento lateral fino (el único toque a color pleno)
            c.setFillColor(col)
            c.rect(left_x, _y(cy_top + card_h), 4, card_h, fill=1, stroke=0)
            # Icono en círculo tenue con símbolo a color (no disco chillón)
            c.setFillColor(_mix(col, BG_CARD, 0.82))
            c.circle(left_x + 32, _y(cy_top + card_h / 2), 11, fill=1, stroke=0)
            _text(c, icon, left_x + 32, cy_top + card_h / 2 + 5,
                  font=FONT_BOLD, size=13, color=_num_of(col), anchor="center")
            # Texto centrado verticalmente (antes flotaba arriba)
            _wrap_vcenter(c, it, left_x + 60, cy_top, card_h,
                          width=col_w - 82, font=FONT_REG, size=15.5,
                          color=TEXT_MD, line_height=1.3, max_lines=2)
            cy_top += card_h + card_gap_y
        return cy_top - card_gap_y  # fin real de la sección

    s_end = _verdict_section(
        "FORTALEZAS", f"{n_s} señales positivas detectadas",
        strengths, GREEN, "✓", top_y)
    _verdict_section(
        "DEBILIDADES", f"{n_w} riesgos a vigilar",
        weaknesses, RED, "!", s_end + section_gap)

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

