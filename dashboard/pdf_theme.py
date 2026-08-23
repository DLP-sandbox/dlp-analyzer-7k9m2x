"""
dashboard/pdf_theme.py — Sistema de diseño del Informe DLP (PDF).

Paleta (espejo de los tokens de styles.py / charts.py), tipografía de marca,
geometría común de las 7 páginas y los componentes vectoriales reutilizables
(tarjetas, semáforos, termómetros, barras nativas, píldoras, tiles, iconos).

Reglas duras de este módulo:
  · Cero llamadas a Anthropic (solo dibuja).
  · Ningún símbolo tipográfico en Bricolage Grotesque (sus TTF no traen ◈ ▲ ● ✓):
    todo icono se dibuja con primitivas vectoriales (círculos, líneas, paths).
  · Coordenadas "top-based": `top` = distancia desde el borde superior; `_y()`
    convierte a la coordenada de ReportLab. En `_text`, `top` es la BASELINE.
"""
from pathlib import Path

from reportlab.lib.colors import Color, HexColor
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ── Geometría de página ──────────────────────────────────────────────────
PAGE_W = 1920.0
PAGE_H = 1080.0
MARGIN_X = 70.0
CONTENT_W = PAGE_W - 2 * MARGIN_X          # 1780

HEADER_RULE_TOP = 118.0                     # regla bajo la cabecera
CONTENT_TOP = 144.0
CONTENT_BOTTOM = 946.0
NAV_TOP = 968.0
NAV_H = 44.0
FOOT_BASE = 1046.0

# ── Paleta — mismos tokens que la app ────────────────────────────────────
BG_DEEP   = HexColor("#0A0B0D")   # --bg
BG_CARD   = HexColor("#101216")   # --surface-1
BG_CARD2  = HexColor("#15181D")   # --surface-2
BG_CTA    = HexColor("#0D0F12")   # --surface-0 (tarjeta del CTA)
BG_RAIL   = HexColor("#1A1E25")   # riel de termómetros y barras
ORANGE    = HexColor("#E2B25C")   # --accent (oro antiguo)
ORANGE_DK = HexColor("#C08E3B")   # --accent-deep
GOLD      = HexColor("#F0C878")   # --accent-hi
GREEN     = HexColor("#3DD68C")   # --pos
GREEN_SOFT = HexColor("#63DFA3")
AMBER_SOFT = HexColor("#E0854E")
RED       = HexColor("#F1495F")   # --neg
BLUE      = HexColor("#6FA3E0")   # --info
TEXT_HI   = HexColor("#F2F3F5")
TEXT_MD   = HexColor("#C9CDD3")
TEXT_LO   = HexColor("#8D949E")
TEXT_DIM  = HexColor("#5E6570")
BORDER    = HexColor("#232830")
INK       = HexColor("#0A0D11")   # texto oscuro sobre oro
CREAM     = HexColor("#F4EBD6")   # tile del QR

# ── Marca / CTA ──────────────────────────────────────────────────────────
CLUB_DLP_URL    = "https://diariolargoplazo.com"
CLUB_DLP_DOMAIN = "diariolargoplazo.com"
CLUB_DLP_HANDLE = "@diariolargoplazo"

DISCLAIMER = ("DLP Analyzer se conecta y analiza en vivo los datos de mercado de cada "
              "acción. Esto no es una recomendación de inversión ni asesoría "
              "financiera personalizada.")

ASSETS_DIR = Path(__file__).parent.parent / "assets"
FONTS_DIR = ASSETS_DIR / "fonts"


# ── Mezclas de color ─────────────────────────────────────────────────────
def _mix(c1: Color, c2: Color, t: float) -> Color:
    """Interpola linealmente entre dos colores. t=0 → c1, t=1 → c2."""
    return Color(c1.red + (c2.red - c1.red) * t,
                 c1.green + (c2.green - c1.green) * t,
                 c1.blue + (c2.blue - c1.blue) * t)


def _border_of(color: Color) -> Color:
    return _mix(color, BG_DEEP, 0.55)


def _tint_of(color: Color) -> Color:
    return _mix(color, BG_CARD, 0.93)


def _num_of(color: Color) -> Color:
    return _mix(color, TEXT_HI, 0.22)


# ── Tipografía de marca ──────────────────────────────────────────────────
def _try_register_fonts() -> tuple[str, str, str, str, str]:
    """Registra las fuentes y devuelve (REG, BOLD, MONO, DISPLAY, DISPLAY_XL).

    Prioridad: (1) fuentes de marca en assets/fonts — Bricolage Grotesque para
    títulos y números, Inter para cuerpo — así el PDF sale IDÉNTICO en el Mac
    del usuario y en Streamlit Cloud; (2) Helvetica Neue del sistema; (3) la
    Helvetica incorporada de ReportLab."""
    candidates = [
        ("Inter",            "Inter-Regular.ttf"),
        ("Inter-Bold",       "Inter-Bold.ttf"),
        ("Bricolage",        "BricolageGrotesque-Regular.ttf"),
        ("Bricolage-Bold",   "BricolageGrotesque-Bold.ttf"),
        ("Bricolage-XBold",  "BricolageGrotesque-ExtraBold.ttf"),
    ]
    for name, fname in candidates:
        path = FONTS_DIR / fname
        if path.exists():
            try:
                pdfmetrics.registerFont(TTFont(name, str(path)))
            except Exception:
                pass

    sys_ttc = Path("/System/Library/Fonts/HelveticaNeue.ttc")
    if sys_ttc.exists():
        for idx, name in ((0, "HelveticaNeue"), (1, "HelveticaNeue-Bold")):
            try:
                pdfmetrics.registerFont(TTFont(name, str(sys_ttc), subfontIndex=idx))
            except Exception:
                pass

    available = set(pdfmetrics.getRegisteredFontNames())
    if "Inter" in available and "Inter-Bold" in available:
        reg, bold = "Inter", "Inter-Bold"
        disp = "Bricolage-Bold" if "Bricolage-Bold" in available else bold
        disp_xl = "Bricolage-XBold" if "Bricolage-XBold" in available else disp
        return reg, bold, bold, disp, disp_xl
    if "HelveticaNeue" in available:
        return "HelveticaNeue", "HelveticaNeue-Bold", "HelveticaNeue-Bold", \
               "HelveticaNeue-Bold", "HelveticaNeue-Bold"
    return "Helvetica", "Helvetica-Bold", "Helvetica-Bold", "Helvetica-Bold", "Helvetica-Bold"


FONT_REG, FONT_BOLD, FONT_MONO, FONT_DISPLAY, FONT_DISPLAY_XL = _try_register_fonts()


# ── Coordenadas y primitivas ─────────────────────────────────────────────
def _y(top: float) -> float:
    """Offset desde el techo → coordenada y de ReportLab."""
    return PAGE_H - top


def _fill_bg(c, color=BG_DEEP):
    c.setFillColor(color)
    c.rect(0, 0, PAGE_W, PAGE_H, fill=1, stroke=0)


def _box(c, x, top, w, h, *, r=10, fill=None, stroke=None, stroke_w=1):
    """Rectángulo redondeado en coordenadas top-based."""
    if fill is not None:
        c.setFillColor(fill)
    if stroke is not None:
        c.setStrokeColor(stroke)
        c.setLineWidth(stroke_w)
    c.roundRect(x, _y(top + h), w, h, r,
                stroke=(1 if stroke is not None else 0),
                fill=(1 if fill is not None else 0))


def _text_w(c, txt, font, size, tracking=0.0) -> float:
    s = str(txt)
    return c.stringWidth(s, font, size) + tracking * max(0, len(s) - 1)


def _text(c, txt, x, top, *, font=None, size=12, color=TEXT_MD, anchor="left",
          tracking=0.0):
    """Texto en coordenadas top-based. `top` es la BASELINE.
    `tracking` = espaciado extra entre caracteres (para versalitas)."""
    if font is None:
        font = FONT_REG
    s = str(txt) if txt is not None else "—"
    c.setFont(font, size)
    c.setFillColor(color)
    y = _y(top)
    if tracking:
        # El espaciado entre caracteres vive en el objeto de texto, no en el canvas.
        tw = _text_w(c, s, font, size, tracking)
        x0 = x - tw / 2 if anchor == "center" else x - tw if anchor == "right" else x
        t = c.beginText(x0, y)
        t.setFont(font, size)
        t.setFillColor(color)
        t.setCharSpace(tracking)
        t.textOut(s)
        # OJO: el espaciado se queda pegado al canvas y ensancharía TODO el
        # texto posterior (+17 % medido). Se resetea dentro y fuera del bloque.
        t.setCharSpace(0)
        c.drawText(t)
        try:
            c._charSpace = 0
        except Exception:
            pass
        return
    if anchor == "center":
        c.drawCentredString(x, y, s)
    elif anchor == "right":
        c.drawRightString(x, y, s)
    else:
        c.drawString(x, y, s)


def _fit_text(c, txt, font, size, width) -> str:
    """Recorta un texto por ancho real (stringWidth) con «…» limpio."""
    s = " ".join(str(txt or "").split())
    if c.stringWidth(s, font, size) <= width:
        return s
    ell = "…"
    while s and c.stringWidth(s + ell, font, size) > width:
        s = s[:-1]
    return s.rstrip(" ,;:.") + ell


def _wrap_lines(c, txt, width, *, font=None, size=12, max_lines=None) -> list:
    """Calcula las líneas de un texto envuelto por palabra (sin dibujar)."""
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
        lines[-1] = last.rstrip(" ,;:.") + "…"
    return lines


def _wrap(c, txt, x, top, width, *, font=None, size=12, color=TEXT_MD,
          line_height=1.38, max_lines=None) -> float:
    """Dibuja texto envuelto. Devuelve la siguiente baseline libre (top-based)."""
    if font is None:
        font = FONT_REG
    lines = _wrap_lines(c, txt, width, font=font, size=size, max_lines=max_lines)
    if not lines:
        return top
    c.setFont(font, size)
    c.setFillColor(color)
    lh = size * line_height
    cy = top
    for ln in lines:
        c.drawString(x, _y(cy), ln)
        cy += lh
    return cy


# ── Escalas de color ─────────────────────────────────────────────────────
def _score_color(score) -> Color:
    """Color de una calificación 0-100 — los MISMOS 5 escalones que charts.py."""
    try:
        s = float(score)
        if s != s:
            return TEXT_LO
    except Exception:
        return TEXT_LO
    if s >= 80:
        return GREEN
    if s >= 65:
        return GREEN_SOFT
    if s >= 50:
        return ORANGE
    if s >= 35:
        return AMBER_SOFT
    return RED


def _rec_palette(rec: str) -> tuple[Color, Color]:
    """(relleno, texto) del chip de la etiqueta — por el valor INTERNO."""
    r = (rec or "").upper()
    if r in ("MUY ATRACTIVO", "STRONG BUY"):
        return GREEN, HexColor("#001A06")
    if r in ("ATRACTIVO", "BUY"):
        return BLUE, TEXT_HI
    if r in ("EVITAR", "PASS", "POCO ATRACTIVO"):
        return RED, TEXT_HI
    return ORANGE, HexColor("#1A0F00")


# ── Semáforo universal ───────────────────────────────────────────────────
class Estado:
    """Un estado del semáforo: nivel (bien/regular/mal/sin/info) + palabra."""
    __slots__ = ("nivel", "palabra")

    def __init__(self, nivel: str, palabra: str = None):
        self.nivel = nivel
        self.palabra = palabra if palabra is not None else _PALABRA.get(nivel, "")

    @property
    def color(self) -> Color:
        return _NIVEL_COLOR.get(self.nivel, TEXT_DIM)


_PALABRA = {"bien": "BIEN", "regular": "REGULAR", "mal": "MAL",
            "sin": "SIN DATO", "info": ""}
_NIVEL_COLOR = {"bien": GREEN, "regular": ORANGE, "mal": RED,
                "sin": TEXT_DIM, "info": BLUE}

BIEN = lambda palabra=None: Estado("bien", palabra)       # noqa: E731
REGULAR = lambda palabra=None: Estado("regular", palabra)  # noqa: E731
MAL = lambda palabra=None: Estado("mal", palabra)         # noqa: E731
SIN_DATO = lambda palabra=None: Estado("sin", palabra)    # noqa: E731
INFO = lambda palabra=None: Estado("info", palabra)       # noqa: E731


# ── Iconos vectoriales ───────────────────────────────────────────────────
def _dot(c, cx, cy_top, r, color, glow=False):
    """Punto de estado. Con `glow`, anillo tenue alrededor (como .meter-dot)."""
    cy = _y(cy_top)
    if glow:
        c.setFillColor(color)
        c.setFillAlpha(0.18)
        c.circle(cx, cy, r + 3.5, stroke=0, fill=1)
        c.setFillAlpha(1)
    c.setFillColor(color)
    c.circle(cx, cy, r, stroke=0, fill=1)


def _icon_diamond(c, cx, cy_top, r, color):
    cy = _y(cy_top)
    p = c.beginPath()
    p.moveTo(cx, cy + r)
    p.lineTo(cx + r, cy)
    p.lineTo(cx, cy - r)
    p.lineTo(cx - r, cy)
    p.close()
    c.setFillColor(color)
    c.drawPath(p, fill=1, stroke=0)


def _icon_check(c, cx, cy_top, r, color, bg=True):
    """Círculo tintado con una marca de verificación en líneas."""
    cy = _y(cy_top)
    if bg:
        c.setFillColor(color)
        c.setFillAlpha(0.16)
        c.circle(cx, cy, r, stroke=0, fill=1)
        c.setFillAlpha(1)
    c.setStrokeColor(color)
    c.setLineWidth(max(1.6, r * 0.22))
    c.setLineCap(1)
    c.setLineJoin(1)
    p = c.beginPath()
    p.moveTo(cx - r * 0.42, cy - r * 0.02)
    p.lineTo(cx - r * 0.10, cy - r * 0.36)
    p.lineTo(cx + r * 0.46, cy + r * 0.34)
    c.drawPath(p, fill=0, stroke=1)
    c.setLineCap(0)
    c.setLineJoin(0)


def _icon_minus(c, cx, cy_top, r, color, bg=True):
    cy = _y(cy_top)
    if bg:
        c.setFillColor(color)
        c.setFillAlpha(0.16)
        c.circle(cx, cy, r, stroke=0, fill=1)
        c.setFillAlpha(1)
    c.setStrokeColor(color)
    c.setLineWidth(max(1.6, r * 0.22))
    c.setLineCap(1)
    c.line(cx - r * 0.45, cy, cx + r * 0.45, cy)
    c.setLineCap(0)


def _icon_triangle(c, cx, cy_top, r, color, up=True):
    cy = _y(cy_top)
    p = c.beginPath()
    if up:
        p.moveTo(cx, cy + r); p.lineTo(cx + r, cy - r * 0.8); p.lineTo(cx - r, cy - r * 0.8)
    else:
        p.moveTo(cx, cy - r); p.lineTo(cx + r, cy + r * 0.8); p.lineTo(cx - r, cy + r * 0.8)
    p.close()
    c.setFillColor(color)
    c.drawPath(p, fill=1, stroke=0)


def _icon_arrow_right(c, x, cy_top, length, color, lw=2.2):
    cy = _y(cy_top)
    c.setStrokeColor(color)
    c.setLineWidth(lw)
    c.setLineCap(1)
    c.line(x, cy, x + length, cy)
    c.line(x + length - 7, cy + 6, x + length, cy)
    c.line(x + length - 7, cy - 6, x + length, cy)
    c.setLineCap(0)


# ── Componentes ──────────────────────────────────────────────────────────
def _card(c, x, top, w, h, *, accent=None, title=None, subtitle=None,
          fill=BG_CARD, stroke=BORDER, r=12) -> float:
    """Tarjeta base. Devuelve el `top` libre bajo el título (o el propio top+pad)."""
    _box(c, x, top, w, h, r=r, fill=fill, stroke=stroke, stroke_w=1)
    if accent is not None:
        c.setFillColor(accent)
        c.roundRect(x, _y(top + h), 4, h, 2, stroke=0, fill=1)
    cy = top + 20
    if title:
        _text(c, title, x + 24, top + 30, font=FONT_DISPLAY, size=12.5,
              color=TEXT_LO, tracking=1.2)
        cy = top + 44
        if subtitle:
            _text(c, subtitle, x + 24, top + 50, font=FONT_REG, size=12, color=TEXT_DIM)
            cy = top + 64
    return cy


def _chip(c, x, top, text, *, fill, color, h=28, size=11.5, font=None,
          pad=14, anchor="left", tracking=1.0) -> float:
    """Píldora de texto. Devuelve su ancho. anchor='right' → x es el borde derecho."""
    font = font or FONT_DISPLAY
    tw = _text_w(c, text, font, size, tracking)
    w = tw + 2 * pad
    x0 = x - w if anchor == "right" else x
    _box(c, x0, top, w, h, r=h / 2, fill=fill)
    _text(c, text, x0 + pad, top + h / 2 + size * 0.36, font=font, size=size,
          color=color, tracking=tracking)
    return w


def _estado_chip(c, x_right, top, estado: Estado, *, size=11.5):
    """Punto + palabra del semáforo, alineado a la derecha en `x_right`.
    `top` = baseline de la palabra."""
    if not estado.palabra:
        _dot(c, x_right - 5, top - size * 0.36, 5, estado.color, glow=True)
        return
    _text(c, estado.palabra, x_right, top, font=FONT_BOLD, size=size,
          color=estado.color, anchor="right", tracking=0.6)
    tw = _text_w(c, estado.palabra, FONT_BOLD, size, 0.6)
    _dot(c, x_right - tw - 13, top - size * 0.36, 5, estado.color, glow=True)


def _meter(c, x, top, w, pct, color, *, h=6):
    """Termómetro: riel + punto en la posición `pct` (0-100)."""
    _box(c, x, top, w, h, r=h / 2, fill=BG_RAIL)
    if pct is None:
        return
    p = max(2.0, min(98.0, float(pct)))
    _dot(c, x + w * p / 100.0, top + h / 2, 6, color, glow=True)


def _rail_zones(c, x, top, w, h):
    """Zonas de calidad tenues 0-50 / 50-65 / 65-80 / 80-100 + guías 65 y 80."""
    zonas = ((0, 50, RED, 0.035), (50, 65, ORANGE, 0.035),
             (65, 80, BLUE, 0.035), (80, 100, GREEN, 0.045))
    for a, b, col, alpha in zonas:
        c.setFillColor(col)
        c.setFillAlpha(alpha)
        c.rect(x + w * a / 100, _y(top + h), w * (b - a) / 100, h, stroke=0, fill=1)
    c.setFillAlpha(1)
    for v, col in ((65, ORANGE), (80, GREEN)):
        c.setStrokeColor(col)
        c.setStrokeAlpha(0.35)
        c.setLineWidth(1)
        c.setDash([3, 3])
        xv = x + w * v / 100
        c.line(xv, _y(top), xv, _y(top + h))
    c.setDash([])
    c.setStrokeAlpha(1)


def _native_bars(c, x, top, w, rows, *, row_h=34, name_size=15, score_size=20,
                 ticks=True, code_w=40) -> float:
    """Barras de calificación 0-100 dibujadas en vectorial.

    rows = [(code|None, nombre, score|None, color|None)]. El nombre se escribe
    SIEMPRE completo (el ancho de etiqueta se calcula con el nombre más largo);
    una fila sin dato lleva el riel vacío y «sin dato» — nunca una barra en 0.
    Devuelve el top libre tras la última fila (y los ticks)."""
    if not rows:
        return top
    label_w = max(c.stringWidth(str(r[1]), FONT_BOLD, name_size) for r in rows)
    has_code = any(r[0] for r in rows)
    lx = x + (code_w if has_code else 0)
    rail_x = lx + label_w + 22
    right_w = _text_w(c, "100", FONT_DISPLAY_XL, score_size) + \
        c.stringWidth("/100", FONT_REG, 10) + 8
    rail_w = (x + w) - right_w - 14 - rail_x
    bar_h = min(14, row_h * 0.42)

    # Zonas de fondo que abarcan todas las filas
    total_h = row_h * len(rows)
    _rail_zones(c, rail_x, top, rail_w, total_h)

    cy = top
    for code, nombre, score, color in rows:
        mid = cy + row_h / 2
        base = mid + name_size * 0.36
        ok = score is not None
        if code:
            _text(c, code, x, base, font=FONT_DISPLAY, size=11.5, color=ORANGE, tracking=0.8)
        _text(c, nombre, lx, base, font=FONT_BOLD, size=name_size,
              color=TEXT_HI if ok else TEXT_DIM)
        _box(c, rail_x, mid - bar_h / 2, rail_w, bar_h, r=bar_h / 2, fill=BG_RAIL)
        if ok:
            s = max(0.0, min(100.0, float(score)))
            col = color or _score_color(s)
            bw = max(bar_h, rail_w * s / 100.0)
            _box(c, rail_x, mid - bar_h / 2, bw, bar_h, r=bar_h / 2, fill=col)
            _text(c, "/100", x + w, base, font=FONT_REG, size=10, color=TEXT_DIM, anchor="right")
            _text(c, f"{s:.0f}", x + w - c.stringWidth("/100", FONT_REG, 10) - 3, base,
                  font=FONT_DISPLAY_XL, size=score_size, color=col, anchor="right")
        else:
            _text(c, "sin dato", x + w, base, font=FONT_REG, size=11, color=TEXT_DIM,
                  anchor="right")
        cy += row_h

    if ticks:
        tb = cy + 12
        for v, col in ((0, TEXT_DIM), (25, TEXT_DIM), (50, TEXT_DIM),
                       (65, ORANGE), (80, GREEN), (100, TEXT_DIM)):
            _text(c, str(v), rail_x + rail_w * v / 100, tb, font=FONT_REG, size=9,
                  color=col, anchor="center")
        cy = tb + 6
    return cy


def _signed_bars(c, x, top, w, rows, *, row_h=34, name_size=13.5, limit=None) -> float:
    """Barras con signo (cero al centro): verde a la derecha, rojo a la izquierda.
    rows = [(nombre, valor|None, formato)] con valor en %."""
    if not rows:
        return top
    vals = [abs(float(r[1])) for r in rows if r[1] is not None]
    lim = limit or (max(vals) if vals else 10.0)
    lim = max(lim, 1.0) * 1.15
    label_w = max(c.stringWidth(str(r[0]), FONT_BOLD, name_size) for r in rows)
    val_w = 74
    rail_x = x + label_w + 18
    rail_w = (x + w) - val_w - 12 - rail_x
    cx = rail_x + rail_w / 2
    bar_h = 12
    cy = top
    # eje cero
    c.setStrokeColor(BORDER)
    c.setLineWidth(1)
    c.line(cx, _y(top), cx, _y(top + row_h * len(rows)))
    for nombre, valor, fmt in rows:
        mid = cy + row_h / 2
        base = mid + name_size * 0.36
        ok = valor is not None
        _text(c, nombre, x, base, font=FONT_BOLD, size=name_size,
              color=TEXT_HI if ok else TEXT_DIM)
        if ok:
            v = float(valor)
            col = GREEN if v >= 0 else RED
            bw = min(rail_w / 2, (rail_w / 2) * abs(v) / lim)
            bw = max(bw, 3)
            bx = cx if v >= 0 else cx - bw
            _box(c, bx, mid - bar_h / 2, bw, bar_h, r=bar_h / 2, fill=col)
            _text(c, fmt.format(v), x + w, base, font=FONT_DISPLAY_XL, size=15,
                  color=col, anchor="right")
        else:
            _text(c, "sin dato", x + w, base, font=FONT_REG, size=11, color=TEXT_DIM,
                  anchor="right")
        cy += row_h
    return cy


def _pill(c, x, top, w, h, label, value, estado: Estado, reading=None, *,
          value_size=24):
    """Píldora de dato: etiqueta, valor grande, semáforo y lectura de una línea."""
    _box(c, x, top, w, h, r=10, fill=BG_CARD2, stroke=BORDER)
    _text(c, _fit_text(c, label, FONT_DISPLAY, 11, w - 40 - 90), x + 18, top + 26,
          font=FONT_DISPLAY, size=11, color=TEXT_LO, tracking=1.0)
    _estado_chip(c, x + w - 18, top + 26, estado, size=10.5)
    val_txt = _fit_text(c, value if value not in (None, "") else "—",
                        FONT_DISPLAY_XL, value_size, w - 36)
    _text(c, val_txt, x + 18, top + 30 + value_size, font=FONT_DISPLAY_XL,
          size=value_size, color=TEXT_HI if estado.nivel != "sin" else TEXT_DIM)
    if reading:
        _text(c, _fit_text(c, reading, FONT_REG, 12, w - 36), x + 18, top + h - 16,
              font=FONT_REG, size=12, color=TEXT_MD)


def _metric_tile(c, x, top, w, h, spec: dict):
    """Tile de métrica fundamental: etiqueta · semáforo · valor · termómetro ·
    frase explicativa · «qué mide». `spec` lo produce pdf_rules._evaluar_metrica."""
    estado: Estado = spec["estado"]
    _box(c, x, top, w, h, r=12, fill=BG_CARD, stroke=BORDER)
    c.setFillColor(estado.color)
    c.setFillAlpha(0.9 if estado.nivel != "sin" else 0.35)
    c.roundRect(x, _y(top + h), 4, h, 2, stroke=0, fill=1)
    c.setFillAlpha(1)

    _text(c, spec["label"], x + 24, top + 34, font=FONT_DISPLAY, size=12.5,
          color=TEXT_LO, tracking=1.2)
    _estado_chip(c, x + w - 22, top + 34, estado)

    val_color = TEXT_HI if estado.nivel != "sin" else TEXT_DIM
    _text(c, spec["valor_fmt"], x + 24, top + 98, font=FONT_DISPLAY_XL, size=44,
          color=val_color)
    if spec.get("unidad"):
        vw = c.stringWidth(spec["valor_fmt"], FONT_DISPLAY_XL, 44)
        _text(c, spec["unidad"], x + 24 + vw + 8, top + 98, font=FONT_REG, size=13,
              color=TEXT_DIM)

    _meter(c, x + 24, top + 120, w - 48, spec.get("pct_meter"), estado.color)

    next_top = _wrap(c, spec["frase"], x + 24, top + 166, w - 48, font=FONT_REG,
                     size=14, color=TEXT_MD, line_height=1.38, max_lines=3)
    que = spec.get("que_mide")
    if que:
        qy = max(next_top + 14, top + h - 58)
        _text(c, "QUÉ MIDE", x + 24, qy, font=FONT_DISPLAY, size=9.5, color=TEXT_DIM,
              tracking=1.2)
        _wrap(c, que, x + 24, qy + 18, w - 48, font=FONT_REG, size=11.5,
              color=TEXT_DIM, line_height=1.32, max_lines=2)


def _signals(c, x, top, w, h, pros, cons, *, max_each=2, size=13.5,
             pros_title="SEÑALES POSITIVAS", cons_title="SEÑALES DE RIESGO") -> float:
    """Lista de señales reales del análisis (pros en verde, cons en rojo).
    Se adapta al espacio: deja de pintar ítems cuando no caben."""
    cy = top
    lh = size * 1.36
    bottom = top + h
    for title, items, color, icon in ((pros_title, pros, GREEN, _icon_check),
                                      (cons_title, cons, RED, _icon_minus)):
        items = [i for i in (items or []) if i][:max_each]
        if not items:
            continue
        if cy + 40 > bottom:
            break
        _text(c, title, x, cy + 10, font=FONT_DISPLAY, size=10.5, color=color, tracking=1.2)
        cy += 30
        for it in items:
            lines = _wrap_lines(c, it, w - 34, font=FONT_REG, size=size, max_lines=3)
            block = lh * len(lines)
            if cy + block > bottom:
                break
            icon(c, x + 9, cy + size * 0.36 + 1, 8.5, color)
            _wrap(c, " ".join(lines) if len(lines) == 1 else it, x + 30, cy + size * 0.95,
                  w - 34, font=FONT_REG, size=size, color=TEXT_MD, line_height=1.36,
                  max_lines=3)
            cy += block + 10
        cy += 8
    return cy


def _aviso_bloque(c, x, top, w, h, texto):
    """Aviso centrado cuando un bloque no trae datos: nunca una página vacía."""
    _box(c, x, top, w, h, r=12, fill=BG_CARD, stroke=BORDER)
    mid = top + h / 2
    _dot(c, x + w / 2, mid - 26, 7, TEXT_DIM, glow=True)
    lines = _wrap_lines(c, texto, w - 120, font=FONT_REG, size=14, max_lines=3)
    cy = mid + 4
    c.setFont(FONT_REG, 14)
    c.setFillColor(TEXT_LO)
    for ln in lines:
        c.drawCentredString(x + w / 2, _y(cy), ln)
        cy += 20
