"""
dashboard/pdf_vector.py — Gráficas del Informe DLP dibujadas en VECTOR.

Por qué existe: antes las cuatro gráficas se rasterizaban con Plotly + kaleido,
que arranca un Chromium propio. En Streamlit Cloud ese Chromium no tiene las
librerías del sistema que necesita, `fig.to_image()` lanzaba y el código lo
tragaba en silencio → el PDF salía con todo el texto y SIN una sola gráfica.
Aquí se dibuja todo con primitivas de ReportLab: sin Chrome, sin binarios, sin
red. Lo que se ve en un Mac es exactamente lo que se ve en la nube, siempre.

Cero llamadas a Anthropic. Ninguna función lanza: si faltan datos, devuelven
False y quien las llama pinta su aviso.
"""
import math
from datetime import datetime

from dashboard.pdf_theme import (
    _y, _text, _box, _dot, _fit_text, _text_w,
    BG_CARD, BG_CARD2, BG_RAIL, BORDER, ORANGE, GOLD, GREEN, GREEN_SOFT,
    AMBER_SOFT, RED, BLUE, TEXT_HI, TEXT_MD, TEXT_LO, TEXT_DIM, CREAM, INK,
    FONT_REG, FONT_BOLD, FONT_DISPLAY, FONT_DISPLAY_XL,
    _score_color, _mix, _num_of,
)

_MESES = ("ene", "feb", "mar", "abr", "may", "jun",
          "jul", "ago", "sep", "oct", "nov", "dic")


# ═════════════════════════════════════════════════════════════════════════
# Primitivas
# ═════════════════════════════════════════════════════════════════════════
def _pt(cx, cy_top, r, ang_deg):
    """Punto sobre un círculo en coordenadas top-based (0° = derecha, 90° = arriba)."""
    a = math.radians(ang_deg)
    return cx + r * math.cos(a), cy_top - r * math.sin(a)


def _arc(c, cx, cy_top, r, a0, a1, color, width, *, alpha=1.0, segs=100):
    """Arco de un anillo: polilínea de extremos redondeados sobre el radio medio."""
    if abs(a1 - a0) < 0.01:
        return
    c.saveState()
    c.setStrokeColor(color)
    c.setLineWidth(width)
    c.setLineCap(1)
    c.setLineJoin(1)
    if alpha < 1:
        c.setStrokeAlpha(alpha)
    p = c.beginPath()
    n = max(6, int(segs * abs(a1 - a0) / 180))
    for i in range(n + 1):
        ang = a0 + (a1 - a0) * i / n
        px, py = _pt(cx, cy_top, r, ang)
        (p.moveTo if i == 0 else p.lineTo)(px, _y(py))
    c.drawPath(p, stroke=1, fill=0)
    c.restoreState()


def _polyline(c, pts, color, width, *, alpha=1.0, close=False, fill=None,
              fill_alpha=1.0, dash=None):
    """Polilínea/polígono en coordenadas top-based: pts = [(x, top), …]."""
    if len(pts) < 2:
        return
    c.saveState()
    p = c.beginPath()
    p.moveTo(pts[0][0], _y(pts[0][1]))
    for px, py in pts[1:]:
        p.lineTo(px, _y(py))
    if close:
        p.close()
    if fill is not None:
        c.setFillColor(fill)
        c.setFillAlpha(fill_alpha)
    if color is not None:
        c.setStrokeColor(color)
        c.setLineWidth(width)
        c.setLineCap(1)
        c.setLineJoin(1)
        c.setStrokeAlpha(alpha)
    if dash:
        c.setDash(dash)
    c.drawPath(p, stroke=1 if color is not None else 0, fill=1 if fill is not None else 0)
    c.restoreState()


def _fecha_corta(s) -> str:
    """'2026-07-31' → 'jul 2026'. Tolera datetime y formatos raros."""
    try:
        t = str(s)[:10]
        d = datetime.fromisoformat(t)
        return f"{_MESES[d.month - 1]} {d.year}"
    except Exception:
        return str(s)[:7]


def _nice_ticks(lo, hi, n=4):
    """n valores 'redondos' dentro de [lo, hi] para la rejilla."""
    if hi <= lo:
        return [lo]
    paso = (hi - lo) / n
    mag = 10 ** math.floor(math.log10(paso)) if paso > 0 else 1
    for m in (1, 2, 2.5, 5, 10):
        if paso <= mag * m:
            paso = mag * m
            break
    inicio = math.ceil(lo / paso) * paso
    out, v = [], inicio
    while v <= hi + 1e-9 and len(out) < n + 2:
        out.append(v)
        v += paso
    return out or [lo, hi]


# ═════════════════════════════════════════════════════════════════════════
# 1 · Medidor (tacómetro) del puntaje global
# ═════════════════════════════════════════════════════════════════════════
def dibujar_medidor(c, x, top, w, h, score, etiqueta="") -> bool:
    """Arco semicircular con las bandas del termómetro, aguja y número grande."""
    try:
        s = None if score is None else max(0.0, min(100.0, float(score)))
    except Exception:
        s = None

    r = min((w - 96) / 2, h - 118)
    if r < 40:
        return False
    cx = x + w / 2
    cy = top + 26 + r                      # centro del semicírculo (top-based)
    grosor = max(14, r * 0.17)

    # Riel de fondo + bandas de calidad
    _arc(c, cx, cy, r, 180, 0, BG_RAIL, grosor)
    bandas = ((0, 35, RED), (35, 50, AMBER_SOFT), (50, 65, ORANGE),
              (65, 80, GREEN_SOFT), (80, 100, GREEN))
    for lo, hi, col in bandas:
        _arc(c, cx, cy, r, 180 - 180 * lo / 100, 180 - 180 * hi / 100,
             col, grosor, alpha=0.20)

    # Arco de progreso
    if s is not None:
        col = _score_color(s)
        _arc(c, cx, cy, r, 180, 180 - 180 * s / 100, col, grosor)
    else:
        col = TEXT_DIM

    # Marcas 0 · 50 · 100
    for v in (0, 25, 50, 75, 100):
        ang = 180 - 180 * v / 100
        p1 = _pt(cx, cy, r - grosor / 2 - 4, ang)
        p2 = _pt(cx, cy, r - grosor / 2 - 11, ang)
        _polyline(c, [p1, p2], BORDER, 1.4)
        if v in (0, 50, 100):
            lx, ly = _pt(cx, cy, r + 20, ang)
            anchor = "left" if v == 0 else "right" if v == 100 else "center"
            _text(c, str(v), lx, ly + 4, font=FONT_REG, size=10, color=TEXT_DIM,
                  anchor=anchor)

    # Aguja + eje
    if s is not None:
        ang = 180 - 180 * s / 100
        punta = _pt(cx, cy, r - grosor / 2 - 6, ang)
        cola = _pt(cx, cy, -r * 0.12, ang)
        _polyline(c, [cola, punta], TEXT_HI, 3)
        _dot(c, cx, cy, 7, TEXT_HI)
        _dot(c, cx, cy, 3.4, BG_CARD)

    # Número grande + etiqueta
    num = f"{s:.0f}" if s is not None else "—"
    base = cy + 62
    nw = c.stringWidth(num, FONT_DISPLAY_XL, 54)
    sw = c.stringWidth("/100", FONT_REG, 15)
    x0 = cx - (nw + 4 + sw) / 2
    _text(c, num, x0, base, font=FONT_DISPLAY_XL, size=54, color=_num_of(col))
    _text(c, "/100", x0 + nw + 4, base, font=FONT_REG, size=15, color=TEXT_DIM)
    if etiqueta:
        _text(c, _fit_text(c, etiqueta, FONT_DISPLAY, 12, w - 40), cx, base + 24,
              font=FONT_DISPLAY, size=12, color=col, anchor="center", tracking=1.2)
    return True


# ═════════════════════════════════════════════════════════════════════════
# 2 · Perfil de calidad (radar de 5 dimensiones)
# ═════════════════════════════════════════════════════════════════════════
_RADAR_DIMS = [("quality", "Calidad", 90), ("growth", "Crecimiento", 162),
               ("momentum", "Impulso", 234), ("future", "Futuro", 306),
               ("value", "Valor", 18)]


def dibujar_radar(c, x, top, w, h, snowflake) -> bool:
    """Pentágono de calidad: 5 ejes de 0 a 20, anillos de referencia y valores."""
    sn = snowflake if isinstance(snowflake, dict) else {}
    vals = []
    for key, _, _ in _RADAR_DIMS:
        try:
            v = float(sn.get(key))
            v = 10.0 if v != v else max(0.0, min(20.0, v))
        except Exception:
            v = 10.0                        # dimensión sin dato → neutro, nunca 0
        vals.append(v)

    r = min((w - 190) / 2, (h - 78) / 2)
    if r < 34:
        return False
    cx = x + w / 2
    cy = top + h / 2 - 4

    # Anillos + ejes
    for frac in (0.25, 0.5, 0.75, 1.0):
        pts = [_pt(cx, cy, r * frac, ang) for _, _, ang in _RADAR_DIMS]
        _polyline(c, pts, BORDER, 1 if frac < 1 else 1.4, close=True,
                  alpha=0.55 if frac < 1 else 0.9)
    for _, _, ang in _RADAR_DIMS:
        _polyline(c, [(cx, cy), _pt(cx, cy, r, ang)], BORDER, 1, alpha=0.5)

    # Polígono de datos
    total = sum(vals)
    col = GREEN if total >= 70 else ORANGE if total >= 50 else RED
    pts = [_pt(cx, cy, r * v / 20.0, ang) for v, (_, _, ang) in zip(vals, _RADAR_DIMS)]
    _polyline(c, pts, col, 2.4, close=True, fill=col, fill_alpha=0.16)
    for px, py in pts:
        _dot(c, px, py, 3.6, col)

    # Etiquetas con su valor (nombre arriba, "14/20" debajo)
    for v, (_, nombre, ang) in zip(vals, _RADAR_DIMS):
        lx, ly = _pt(cx, cy, r + 26, ang)
        if ang in (18, 306):          # lado derecho
            anchor, lx = "left", lx - 4
        elif ang in (162, 234):       # lado izquierdo
            anchor, lx = "right", lx + 4
        else:                          # vértice superior
            anchor = "center"
        _text(c, nombre, lx, ly, font=FONT_REG, size=11, color=TEXT_LO, anchor=anchor)
        num = f"{v:.0f}"
        w_num = c.stringWidth(num, FONT_DISPLAY_XL, 15)
        w_max = c.stringWidth("/20", FONT_REG, 9)
        total_w = w_num + 2 + w_max
        x_ini = lx if anchor == "left" else lx - total_w if anchor == "right" else lx - total_w / 2
        _text(c, num, x_ini, ly + 17, font=FONT_DISPLAY_XL, size=15, color=col)
        _text(c, "/20", x_ini + w_num + 2, ly + 17, font=FONT_REG, size=9, color=TEXT_DIM)
    return True


# ═════════════════════════════════════════════════════════════════════════
# 3 · Precio: línea con relleno, rejilla y niveles opcionales
# ═════════════════════════════════════════════════════════════════════════
def _serie(a):
    """(fechas, precios) del histórico guardado en el análisis."""
    tech = (getattr(a, "reports", None) or {}).get("technical")
    rd = getattr(tech, "raw_data", None) or {}
    df = rd.get("df_daily", {}) or {}
    close = df.get("Close", {}) if isinstance(df, dict) else {}
    if not isinstance(close, dict) or not close:
        return None, None
    serie = []
    for d in sorted(close.keys()):
        try:
            v = float(close[d])
            if v == v and v > 0:
                serie.append((d, v))
        except Exception:
            continue
    if len(serie) < 20:
        return None, None
    return [s[0] for s in serie], [s[1] for s in serie]


def dibujar_precio(c, x, top, w, h, a, *, niveles=None) -> bool:
    """Línea del precio. `niveles` = [(valor, nombre, color)] para el recorrido."""
    fechas, precios = _serie(a)
    if not fechas:
        return False

    gutter_izq = 66
    gutter_der = 128 if niveles else 22
    gutter_bajo = 30
    px0 = x + gutter_izq
    px1 = x + w - gutter_der
    py0 = top + 10                      # arriba del área de trazado
    py1 = top + h - gutter_bajo         # abajo
    if px1 - px0 < 80 or py1 - py0 < 60:
        return False

    puntos_y = list(precios) + [v for v, _, _ in (niveles or []) if v is not None]
    lo, hi = min(puntos_y), max(puntos_y)
    pad = (hi - lo) * 0.10 or (hi * 0.05 or 1.0)
    y_lo, y_hi = max(0.0, lo - pad), hi + pad
    span = (y_hi - y_lo) or 1.0

    def sx(i):
        return px0 + (px1 - px0) * i / max(1, len(precios) - 1)

    def sy(v):
        return py1 - (py1 - py0) * (v - y_lo) / span

    # Rejilla + etiquetas de precio
    for v in _nice_ticks(y_lo, y_hi, 4):
        if not (y_lo <= v <= y_hi):
            continue
        yy = sy(v)
        _polyline(c, [(px0, yy), (px1, yy)], TEXT_HI, 1, alpha=0.06)
        _text(c, f"${v:,.0f}" if v >= 10 else f"${v:,.2f}", px0 - 12, yy + 4,
              font=FONT_REG, size=11, color=TEXT_DIM, anchor="right")

    # Etiquetas de fecha
    n = len(fechas)
    idxs = [0, n // 4, n // 2, (3 * n) // 4, n - 1]
    for k, i in enumerate(idxs):
        anchor = "left" if k == 0 else "right" if k == len(idxs) - 1 else "center"
        _text(c, _fecha_corta(fechas[i]), sx(i), py1 + 20, font=FONT_REG, size=11,
              color=TEXT_DIM, anchor=anchor)

    # Relleno bajo la línea + línea + halo
    pts = [(sx(i), sy(v)) for i, v in enumerate(precios)]
    _polyline(c, [(pts[0][0], py1)] + pts + [(pts[-1][0], py1)], None, 0,
              close=True, fill=ORANGE, fill_alpha=0.09)
    _polyline(c, pts, ORANGE, 6.5, alpha=0.13)
    _polyline(c, pts, ORANGE, 2.4)

    # Punto del último precio
    _dot(c, pts[-1][0], pts[-1][1], 5.5, GOLD, glow=True)
    c.setStrokeColor(TEXT_HI)
    c.setLineWidth(1.6)
    c.circle(pts[-1][0], _y(pts[-1][1]), 5.5, stroke=1, fill=0)

    # Niveles horizontales con etiquetas que nunca se pisan
    if niveles:
        items = [(float(v), nombre, col) for v, nombre, col in niveles if v is not None]
        items.sort(key=lambda t: t[0])
        MIN_SEP = 40.0
        ys = [sy(v) for v, _, _ in items]
        for i in range(len(ys) - 2, -1, -1):          # de abajo (mayor top) hacia arriba
            if ys[i] - ys[i + 1] < MIN_SEP:
                ys[i] = ys[i + 1] + MIN_SEP
        exceso = (py0 + 16) - ys[-1]
        if exceso > 0:
            ys = [yy + exceso for yy in ys]
            for i in range(len(ys) - 2, -1, -1):
                if ys[i] - ys[i + 1] < MIN_SEP:
                    ys[i] = ys[i + 1] + MIN_SEP
        for (valor, nombre, col), y_lbl in zip(items, ys):
            yy = sy(valor)
            _polyline(c, [(px0, yy), (px1, yy)], col, 1.8, dash=[6, 5], alpha=0.95)
            _polyline(c, [(px1, yy), (px1 + 12, y_lbl)], col, 1, alpha=0.5)
            _text(c, nombre, px1 + 18, y_lbl - 3, font=FONT_DISPLAY, size=11,
                  color=col, tracking=0.8)
            _text(c, f"${valor:,.2f}", px1 + 18, y_lbl + 16, font=FONT_DISPLAY_XL,
                  size=16, color=_num_of(col))
    return True


# ═════════════════════════════════════════════════════════════════════════
# 4 · QR vectorial (sin PIL): módulos dibujados como rectángulos
# ═════════════════════════════════════════════════════════════════════════
def dibujar_qr(c, url, x, top, size, *, fg=INK, bg=CREAM, radio=14) -> bool:
    """QR nítido a cualquier escala y sin depender de PIL."""
    try:
        import qrcode
        qr = qrcode.QRCode(version=None,
                           error_correction=qrcode.constants.ERROR_CORRECT_M,
                           box_size=10, border=2)
        qr.add_data(url)
        qr.make(fit=True)
        matriz = qr.get_matrix()
    except Exception:
        return False
    n = len(matriz)
    if not n:
        return False
    _box(c, x, top, size, size, r=radio, fill=bg)
    util = size * 0.86
    m = util / n
    x0 = x + (size - util) / 2
    y0 = top + (size - util) / 2
    c.setFillColor(fg)
    for fila, valores in enumerate(matriz):
        col_ini = None
        for col in range(n + 1):
            v = valores[col] if col < n else False
            if v and col_ini is None:
                col_ini = col
            elif not v and col_ini is not None:
                ancho = (col - col_ini) * m
                c.rect(x0 + col_ini * m, _y(y0 + (fila + 1) * m), ancho + 0.25, m + 0.25,
                       stroke=0, fill=1)
                col_ini = None
    return True
