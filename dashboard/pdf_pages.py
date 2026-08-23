"""
dashboard/pdf_pages.py — Las 7 páginas del Informe DLP.

Cada página comparte cabecera (marca · ticker · etiqueta · nota · fecha), pie
(disclaimer · paginación) y la barra de navegación clicable con las 7 secciones.
Cero llamadas a Anthropic: solo lee el StockAnalysis y dibuja.
"""
from dashboard.pdf_theme import (
    PAGE_W, PAGE_H, MARGIN_X, CONTENT_W, HEADER_RULE_TOP, CONTENT_TOP, CONTENT_BOTTOM,
    NAV_TOP, NAV_H, FOOT_BASE,
    BG_DEEP, BG_CARD, BG_CARD2, BG_CTA, BG_RAIL, ORANGE, ORANGE_DK, GOLD, GREEN, RED, BLUE,
    TEXT_HI, TEXT_MD, TEXT_LO, TEXT_DIM, BORDER, INK, CREAM,
    CLUB_DLP_URL, CLUB_DLP_DOMAIN, CLUB_DLP_HANDLE, DISCLAIMER,
    FONT_REG, FONT_BOLD, FONT_DISPLAY, FONT_DISPLAY_XL,
    _y, _fill_bg, _box, _text, _text_w, _fit_text, _wrap, _wrap_lines,
    _score_color, _rec_palette, _num_of, _border_of, _mix,
    BIEN, REGULAR, MAL, SIN_DATO, INFO, Estado,
    _dot, _icon_diamond, _icon_check, _icon_minus, _icon_arrow_right,
    _card, _chip, _estado_chip, _meter, _native_bars, _signed_bars, _pill,
    _metric_tile, _signals, _aviso_bloque,
)
from dashboard.pdf_rules import (
    SECCIONES, BLOQUES, _rep, _rep_ok, _km, _rd, _score, _pros, _cons,
    _score_rows, _pilares, _to_float, _limpiar, _enum_es, _es_sector, _negocio,
    _verdict_stability, _verdict_trend, _verdict_asymmetry, _verdict_generic,
    _conclusion, _fundamentales_specs, _pills_technical, _vs_mercado_rows,
    _niveles_clave, _pills_future, _pills_institutional, _pills_catalysts,
    _pills_macro, _pills_sentiment, _precios, _plan_posicion, _tesis_parrafos,
    _horizonte, _fecha_es, _money, _truncate_by_sentence,
)
from dashboard.pdf_charts import (
    LOGO_PATH, _chart_png, _chart_png_fiel, _styled_logo_png, _qr_image,
    _build_simple_price_chart, _build_price_journey_chart,
)

TOTAL = len(SECCIONES)
_CONV_ES = {"HIGH": "ALTA", "MEDIUM": "MEDIA", "LOW": "BAJA"}
_AVISO_BLOQUE = ("Este bloque no pudo analizarse esta vez: la fuente de datos no respondió. "
                 "No afecta la calificación global, que se calcula solo con los bloques medidos.")


def _rec_txt(a) -> str:
    try:
        from config.settings import rec_display
        return rec_display(getattr(a, "recommendation", "") or "")
    except Exception:
        return str(getattr(a, "recommendation", "") or "")


# ═════════════════════════════════════════════════════════════════════════
# Marco común: cabecera · pie · navegación
# ═════════════════════════════════════════════════════════════════════════
def _bookmark(c, n: int):
    c.bookmarkPage(f"pg{n}")


def _header(c, a, n: int):
    _fill_bg(c)
    # Marca
    _icon_diamond(c, MARGIN_X + 7, 84, 6.5, ORANGE)
    _text(c, "DLP MARKET ANALYZER", MARGIN_X + 22, 89, font=FONT_DISPLAY, size=13,
          color=ORANGE, tracking=1.8)
    # Ticker · nombre
    tk = str(getattr(a, "ticker", "") or "")
    x_tk = MARGIN_X + 300
    _text(c, tk, x_tk, 92, font=FONT_DISPLAY_XL, size=24, color=TEXT_HI)
    tw = c.stringWidth(tk, FONT_DISPLAY_XL, 24)
    name = _fit_text(c, getattr(a, "company_name", "") or "", FONT_REG, 14, 520)
    _text(c, name, x_tk + tw + 14, 92, font=FONT_REG, size=14, color=TEXT_LO)
    # Derecha: fecha · nota · chip de etiqueta
    right = PAGE_W - MARGIN_X
    _text(c, f"Análisis del {_fecha_es(getattr(a, 'timestamp', ''))}", right, 62,
          font=FONT_REG, size=10.5, color=TEXT_DIM, anchor="right")
    sc = _to_float(getattr(a, "composite_score", None))
    col = _score_color(sc)
    _text(c, "/100", right, 92, font=FONT_REG, size=11, color=TEXT_DIM, anchor="right")
    sw = c.stringWidth("/100", FONT_REG, 11)
    stxt = f"{sc:.1f}" if sc is not None else "—"
    _text(c, stxt, right - sw - 4, 92, font=FONT_DISPLAY_XL, size=24, color=col, anchor="right")
    scw = c.stringWidth(stxt, FONT_DISPLAY_XL, 24)
    fill, tcol = _rec_palette(getattr(a, "recommendation", "") or "")
    _chip(c, right - sw - 4 - scw - 22, 70, _rec_txt(a), fill=fill, color=tcol,
          h=30, size=11.5, anchor="right")
    # Regla
    c.setStrokeColor(BORDER)
    c.setLineWidth(1)
    c.line(MARGIN_X, _y(HEADER_RULE_TOP), PAGE_W - MARGIN_X, _y(HEADER_RULE_TOP))


def _footer_nav(c, n: int):
    # Píldoras de navegación (enlaces internos a cada página)
    size, pad, gap, h = 11, 16, 10, 34
    labels = [f"{s['n']} · {s['nav']}" for s in SECCIONES]
    widths = [_text_w(c, l, FONT_DISPLAY, size, 1.0) + 2 * pad for l in labels]
    total = sum(widths) + gap * (len(labels) - 1)
    x = (PAGE_W - total) / 2
    top = NAV_TOP + (NAV_H - h) / 2
    for s, label, w in zip(SECCIONES, labels, widths):
        activa = s["n"] == n
        _box(c, x, top, w, h, r=h / 2, fill=ORANGE if activa else BG_CARD2,
             stroke=None if activa else BORDER)
        _text(c, label, x + pad, top + h / 2 + size * 0.36, font=FONT_DISPLAY, size=size,
              color=INK if activa else TEXT_LO, tracking=1.0)
        if not activa:
            c.linkAbsolute("", f"pg{s['n']}", (x, _y(top + h), x + w, _y(top)))
        x += w + gap
    # Pie
    _text(c, f"{CLUB_DLP_DOMAIN}  ·  pulsa una sección para ir a ella", MARGIN_X, FOOT_BASE,
          font=FONT_REG, size=10, color=TEXT_DIM)
    _text(c, DISCLAIMER, PAGE_W / 2, FOOT_BASE, font=FONT_REG, size=9.5, color=TEXT_DIM,
          anchor="center")
    _text(c, f"{n} / {TOTAL}", PAGE_W - MARGIN_X, FOOT_BASE, font=FONT_DISPLAY, size=11,
          color=TEXT_LO, anchor="right", tracking=1.0)


def _section_header(c, sec: dict, *, score=None, verdict=None, estado: Estado = None,
                    top=CONTENT_TOP, h=92, right_chip=None) -> float:
    """Banda de cabecera de un bloque. Devuelve el top libre (tras la teoría)."""
    x, w = MARGIN_X, CONTENT_W
    _box(c, x, top, w, h, r=14, fill=BG_CARD, stroke=BORDER)
    cx = x + 26
    if sec.get("code"):
        cw = _chip(c, cx, top + 22, sec["code"], fill=ORANGE, color=INK, h=34, size=14,
                   pad=13, tracking=1.2)
        cx += cw + 18
    _text(c, sec["titulo"], cx, top + 50, font=FONT_DISPLAY_XL, size=34, color=TEXT_HI)
    _text(c, sec.get("subtitulo", ""), cx, top + 76, font=FONT_REG, size=15, color=TEXT_LO)

    right = x + w - 26
    if score is not None:
        col = _score_color(score)
        _text(c, "/100", right, top + 62, font=FONT_REG, size=13, color=TEXT_DIM, anchor="right")
        sw = c.stringWidth("/100", FONT_REG, 13)
        _text(c, f"{score:.0f}", right - sw - 6, top + 62, font=FONT_DISPLAY_XL, size=54,
              color=col, anchor="right")
        right -= sw + 6 + c.stringWidth(f"{score:.0f}", FONT_DISPLAY_XL, 54) + 40
    elif right_chip:
        cw = _chip(c, right, top + 29, right_chip, fill=BG_CARD2, color=TEXT_MD, h=34,
                   size=12, anchor="right")
        right -= cw + 40
    if verdict and estado is not None:
        tw = c.stringWidth(verdict, FONT_BOLD, 16)
        _text(c, verdict, right, top + 52, font=FONT_BOLD, size=16, color=TEXT_HI, anchor="right")
        _dot(c, right - tw - 16, top + 52 - 16 * 0.36, 7, estado.color, glow=True)
        if estado.palabra:
            _text(c, estado.palabra, right, top + 72, font=FONT_DISPLAY, size=10.5,
                  color=estado.color, anchor="right", tracking=1.2)
    teoria = sec.get("teoria")
    if teoria:
        _text(c, teoria, x + 2, top + h + 22, font=FONT_REG, size=12.5, color=TEXT_DIM)
        return top + h + 34
    return top + h + 18


def _mini_header(c, x, top, w, code, titulo, subtitulo, score, verdict=None, estado=None):
    """Cabecera compacta de un sub-bloque (media página o columna)."""
    cx = x
    if code:
        cw = _chip(c, cx, top + 2, code, fill=ORANGE, color=INK, h=28, size=12, pad=11)
        cx += cw + 14
    _text(c, titulo, cx, top + 24, font=FONT_DISPLAY_XL, size=24, color=TEXT_HI)
    _text(c, subtitulo, x, top + 50, font=FONT_REG, size=12.5, color=TEXT_LO)
    if score is not None:
        col = _score_color(score)
        _text(c, "/100", x + w, top + 28, font=FONT_REG, size=11, color=TEXT_DIM, anchor="right")
        sw = c.stringWidth("/100", FONT_REG, 11)
        _text(c, f"{score:.0f}", x + w - sw - 4, top + 28, font=FONT_DISPLAY_XL, size=40,
              color=col, anchor="right")
    if verdict and estado is not None:
        tw = c.stringWidth(verdict, FONT_BOLD, 12.5)
        _text(c, verdict, x + w, top + 52, font=FONT_BOLD, size=12.5, color=TEXT_MD, anchor="right")
        _dot(c, x + w - tw - 12, top + 52 - 12.5 * 0.36, 5, estado.color, glow=True)


def _pills_grid(c, x, top, w, pills, *, cols=2, h=84, gap=12) -> float:
    pw = (w - gap * (cols - 1)) / cols
    for i, p in enumerate(pills):
        r, col = divmod(i, cols)
        _pill(c, x + col * (pw + gap), top + r * (h + gap), pw, h,
              p["label"], p["value"], p["estado"], p.get("reading"))
    rows = (len(pills) + cols - 1) // cols
    return top + rows * h + (rows - 1) * gap


def _text_card(c, x, top, w, h, title, text, *, size=13.5, max_lines=None) -> float:
    cy = _card(c, x, top, w, h, title=title)
    if not text:
        _text(c, "Sin datos esta vez.", x + 24, cy + 22, font=FONT_REG, size=size, color=TEXT_DIM)
        return cy + 40
    lh = size * 1.38
    if max_lines is None:
        max_lines = max(1, int((top + h - 18 - cy - 6) // lh))
    return _wrap(c, text, x + 24, cy + 18, w - 48, font=FONT_REG, size=size, color=TEXT_MD,
                 line_height=1.38, max_lines=max_lines)


def _draw_fig(c, fig, x, top, w, h, *, fiel=False, px_w=900, px_h=600, scale=2):
    """Rasteriza y encaja una figura en un área (aspecto preservado, centrado)."""
    if fig is None:
        return False
    img = _chart_png_fiel(fig, px_w, px_h, scale) if fiel else _chart_png(fig, px_w, px_h)
    if img is None:
        return False
    c.drawImage(img, x, _y(top + h), width=w, height=h, preserveAspectRatio=True,
                anchor="c", mask="auto")
    return True


# ═════════════════════════════════════════════════════════════════════════
# P1 · VEREDICTO
# ═════════════════════════════════════════════════════════════════════════
def _pagina_1_veredicto(c, a):
    n = 1
    _bookmark(c, n)
    _header(c, a, n)
    x, w = MARGIN_X, CONTENT_W
    sc = _to_float(getattr(a, "composite_score", None))
    col = _score_color(sc)

    # ── Hero ───────────────────────────────────────────────────────────
    top, h = CONTENT_TOP, 160
    _box(c, x, top, w, h, r=14, fill=BG_CARD, stroke=_border_of(ORANGE))
    c.setFillColor(ORANGE)
    c.roundRect(x, _y(top + h), 5, h, 2.5, stroke=0, fill=1)
    tk = str(getattr(a, "ticker", "") or "")
    _text(c, tk, x + 40, top + 92, font=FONT_DISPLAY_XL, size=72, color=ORANGE)
    tkw = c.stringWidth(tk, FONT_DISPLAY_XL, 72)
    name = _fit_text(c, getattr(a, "company_name", "") or "", FONT_BOLD, 24, 760)
    _text(c, name, x + 40 + tkw + 24, top + 92, font=FONT_BOLD, size=24, color=TEXT_HI)
    sector_txt = _es_sector(getattr(a, "sector", ""))
    negocio = _negocio(getattr(a, "sector", ""))
    if negocio and sector_txt and negocio.strip().lower() == sector_txt.strip().lower():
        negocio = ""                      # sin industria, la frase repetiría el sector
    partes = [p for p in (sector_txt, negocio, "Pensado para el largo plazo") if p]
    _text(c, _fit_text(c, "   ·   ".join(partes), FONT_REG, 14, 1000), x + 42, top + 128,
          font=FONT_REG, size=14, color=TEXT_LO)

    right = x + w - 40
    _text(c, f"{sc:.1f}" if sc is not None else "—", right, top + 86, font=FONT_DISPLAY_XL,
          size=82, color=_num_of(col), anchor="right")
    _text(c, "PUNTAJE GLOBAL  /  100", right, top + 116, font=FONT_DISPLAY, size=11.5,
          color=TEXT_LO, anchor="right", tracking=1.6)
    cx = right
    fill, tcol = _rec_palette(getattr(a, "recommendation", "") or "")
    cx -= _chip(c, cx, top + 125, _rec_txt(a), fill=fill, color=tcol, h=28, size=11.5, anchor="right") + 10
    conv = _CONV_ES.get(str(getattr(a, "conviction_level", "") or "").upper())
    if conv:
        cx -= _chip(c, cx, top + 125, f"CONVICCIÓN {conv}", fill=BG_CARD2, color=TEXT_MD,
                    h=28, size=11, anchor="right") + 10
    if getattr(a, "is_compound_machine", False):
        _chip(c, cx, top + 125, "COMPOUNDER", fill=GOLD, color=INK, h=28, size=11, anchor="right")

    # ── Fila 2: medidor · perfil · desglose nativo ─────────────────────
    top2, h2 = top + h + 16, 344
    gw, sw_ = 440, 440
    gap = 18
    dw = w - gw - sw_ - 2 * gap
    cy = _card(c, x, top2, gw, h2, title="PUNTAJE DLP",
               subtitle=f"Calificación global · {_rec_txt(a)}")
    try:
        from dashboard.charts import build_gauge
        fig = build_gauge(sc if sc is not None else 50, getattr(a, "recommendation", "") or "")
        _draw_fig(c, fig, x + 16, cy + 4, gw - 32, top2 + h2 - cy - 18, fiel=True,
                  px_w=520, px_h=440, scale=4)
    except Exception:
        pass
    x2 = x + gw + gap
    cy = _card(c, x2, top2, sw_, h2, title="PERFIL DE CALIDAD",
               subtitle="Cinco dimensiones · 0–20 puntos cada una")
    try:
        from dashboard.charts import build_snowflake
        fig = build_snowflake(getattr(a, "snowflake", None) or {})
        _draw_fig(c, fig, x2 + 16, cy + 4, sw_ - 32, top2 + h2 - cy - 18, fiel=True,
                  px_w=520, px_h=460, scale=4)
    except Exception:
        pass
    x3 = x2 + sw_ + gap
    cy = _card(c, x3, top2, dw, h2, title="DESGLOSE POR ANÁLISIS",
               subtitle="Los ocho bloques del análisis · 0–100 cada uno")
    rows = _score_rows(a)
    row_h = (top2 + h2 - 14 - 22 - (cy + 8)) / len(rows)
    _native_bars(c, x3 + 24, cy + 8, dw - 48, rows, row_h=row_h, name_size=15, score_size=20)

    # ── Fila 3: la tesis ───────────────────────────────────────────────
    top3, h3 = top2 + h2 + 16, 176
    _box(c, x, top3, w, h3, r=12, fill=BG_CARD, stroke=_border_of(ORANGE))
    c.setFillColor(ORANGE)
    c.roundRect(x, _y(top3 + h3), 4, h3, 2, stroke=0, fill=1)
    _text(c, "LA TESIS", x + 28, top3 + 30, font=FONT_DISPLAY, size=12.5, color=ORANGE, tracking=1.4)
    parrafos = _tesis_parrafos(a)
    if not parrafos:
        parrafos = [(f"Puntaje global de {sc:.0f}/100. " if sc is not None else "") +
                    "Revisa en las páginas siguientes qué pesa a favor y qué pesa en contra: "
                    "cada bloque trae su calificación, sus señales y su lectura en palabras simples."]
    size, lh, gap_p = 14.5, 20.0, 8.0
    tw_ = w - 56
    avail = top3 + h3 - 16 - (top3 + 56)
    max_total = int((avail + gap_p) // lh)
    p1_lines = _wrap_lines(c, parrafos[0], tw_, font=FONT_REG, size=size, max_lines=max_total)
    cy = _wrap(c, " ".join(p1_lines).replace(" …", "…") if len(p1_lines) < max_total else parrafos[0],
               x + 28, top3 + 56, tw_, font=FONT_REG, size=size, color=TEXT_MD,
               line_height=lh / size, max_lines=max_total)
    if len(parrafos) > 1:
        restantes = int((top3 + h3 - 16 - (cy + gap_p) + (lh - size)) // lh)
        if restantes >= 1:
            _wrap(c, parrafos[1], x + 28, cy + gap_p, tw_, font=FONT_REG, size=size,
                  color=TEXT_MD, line_height=lh / size, max_lines=restantes)

    # ── Fila 4: precios ────────────────────────────────────────────────
    top4, h4 = top3 + h3 + 16, 62
    p = _precios(a)
    tw3 = (w - 32) / 3
    fecha = _fecha_es(getattr(a, "timestamp", ""))
    tiles = [
        ("PRECIO ACTUAL", ORANGE, _money(p["actual"]), f"al cierre del análisis · {fecha}"),
        ("PRECIO MÍNIMO", RED, _money(p["stop"]),
         (f"{p['down']:+.1f}% desde el actual · nivel de protección" if p["down"] is not None
          else "nivel de protección")),
        ("PRECIO POTENCIAL", GREEN, _money(p["target"]),
         (f"{p['up']:+.1f}% desde el actual · precio objetivo" if p["up"] is not None
          else "precio objetivo")),
    ]
    for i, (lab, colr, val, sub) in enumerate(tiles):
        tx = x + i * (tw3 + 16)
        _box(c, tx, top4, tw3, h4, r=10, fill=BG_CARD, stroke=BORDER)
        _dot(c, tx + 22, top4 + h4 / 2, 5.5, colr, glow=True)
        _text(c, lab, tx + 38, top4 + 26, font=FONT_DISPLAY, size=11, color=TEXT_LO, tracking=1.2)
        _text(c, val, tx + 38, top4 + 50, font=FONT_DISPLAY_XL, size=22, color=_num_of(colr))
        _text(c, sub, tx + tw3 - 20, top4 + 40, font=FONT_REG, size=11.5, color=TEXT_DIM, anchor="right")

    _footer_nav(c, n)


# ═════════════════════════════════════════════════════════════════════════
# P2 · FUNDAMENTALES
# ═════════════════════════════════════════════════════════════════════════
def _pagina_2_fundamentales(c, a):
    n = 2
    _bookmark(c, n)
    _header(c, a, n)
    sec = SECCIONES[1]
    r = _rep(a, "fundamentals")
    s = _score(r)
    verdict, est = _verdict_stability(s) if s is not None else ("Bloque sin datos", SIN_DATO())
    body_top = _section_header(c, sec, score=s, verdict=verdict, estado=est)
    x, w = MARGIN_X, CONTENT_W
    body_h = CONTENT_BOTTOM - body_top

    if not _rep_ok(r):
        _aviso_bloque(c, x, body_top, w, body_h, _AVISO_BLOQUE)
        _footer_nav(c, n)
        return

    left_w = 1180
    gap = 16
    tile_w = (left_w - 2 * gap) / 3
    tile_h = (body_h - gap) / 2
    specs = _fundamentales_specs(a)
    for i, spec in enumerate(specs):
        row, col = divmod(i, 3)
        _metric_tile(c, x + col * (tile_w + gap), body_top + row * (tile_h + gap),
                     tile_w, tile_h, spec)

    rx = x + left_w + 18
    rw = w - left_w - 18
    ph = 296
    cy = _card(c, rx, body_top, rw, ph, title="PILARES DEL NEGOCIO",
               subtitle="Sub-calificaciones del bloque · 0–100")
    _native_bars(c, rx + 24, cy + 10, rw - 48, _pilares(a, "fundamentals"), row_h=38,
                 name_size=14, score_size=18, ticks=True)
    sy = body_top + ph + gap
    sh = CONTENT_BOTTOM - sy
    cy = _card(c, rx, sy, rw, sh, title="SEÑALES DEL ANÁLISIS",
               subtitle="Lo que más pesa, en palabras del analista")
    pros, cons = _pros(r, 2), _cons(r, 2)
    if not pros and not cons:
        pros = [_conclusion("fundamentals", s)]
    _signals(c, rx + 24, cy + 2, rw - 48, sy + sh - cy - 14, pros, cons, max_each=2)
    _footer_nav(c, n)


# ═════════════════════════════════════════════════════════════════════════
# P3 · TÉCNICO
# ═════════════════════════════════════════════════════════════════════════
def _pagina_3_tecnico(c, a):
    n = 3
    _bookmark(c, n)
    _header(c, a, n)
    sec = SECCIONES[2]
    r = _rep(a, "technical")
    s = _score(r)
    di = _rd(r).get("daily_indicators") or {}
    stage = di.get("stage", _km(r).get("stage"))
    verdict, est = _verdict_trend(s, stage) if s is not None else ("Bloque sin datos", SIN_DATO())
    body_top = _section_header(c, sec, score=s, verdict=verdict, estado=est)
    x, w = MARGIN_X, CONTENT_W
    body_h = CONTENT_BOTTOM - body_top
    if not _rep_ok(r):
        _aviso_bloque(c, x, body_top, w, body_h, _AVISO_BLOQUE)
        _footer_nav(c, n)
        return

    left_w, gap = 1180, 16
    ch = 418
    cy = _card(c, x, body_top, left_w, ch, title="TENDENCIA DEL PRECIO",
               subtitle="Últimos dos años · cierre diario")
    ok = _draw_fig(c, _build_simple_price_chart(a), x + 16, cy + 2, left_w - 32,
                   body_top + ch - cy - 16, px_w=1700, px_h=int(1700 * (ch - 70) / (left_w - 32)))
    if not ok:
        _text(c, "Sin histórico de precios suficiente esta vez.", x + 24, cy + 40,
              font=FONT_REG, size=14, color=TEXT_DIM)
    py = body_top + ch + gap
    ph = 114
    pills = _pills_technical(a)
    pw = (left_w - 3 * 14) / 4
    for i, p in enumerate(pills[:4]):
        _pill(c, x + i * (pw + 14), py, pw, ph, p["label"], p["value"], p["estado"], p["reading"])
    ky = py + ph + gap
    kh = CONTENT_BOTTOM - ky
    cy = _card(c, x, ky, left_w, kh, title="NIVELES QUE IMPORTAN")
    niveles = _niveles_clave(a)
    if niveles:
        colw = (left_w - 48) / len(niveles)
        for i, (lab, txt) in enumerate(niveles):
            lx = x + 24 + i * colw
            _text(c, lab.upper(), lx, cy + 10, font=FONT_DISPLAY, size=10, color=ORANGE, tracking=1.2)
            _wrap(c, txt, lx, cy + 28, colw - 20, font=FONT_REG, size=12, color=TEXT_MD,
                  line_height=1.3, max_lines=2)
    else:
        _text(c, "Sin niveles calculados esta vez.", x + 24, cy + 22, font=FONT_REG, size=13,
              color=TEXT_DIM)

    rx = x + left_w + 18
    rw = w - left_w - 18
    vh = 300
    cy = _card(c, rx, body_top, rw, vh, title="FRENTE AL MERCADO",
               subtitle="Distancia a sus medias y fuerza relativa")
    _signed_bars(c, rx + 24, cy + 12, rw - 48, _vs_mercado_rows(a), row_h=44)
    sy = body_top + vh + gap
    sh = CONTENT_BOTTOM - sy
    cy = _card(c, rx, sy, rw, sh, title="SEÑALES DEL ANÁLISIS")
    pros, cons = _pros(r, 2), _cons(r, 2)
    if not pros and not cons:
        pros = [_conclusion("technical", s)]
    _signals(c, rx + 24, cy + 2, rw - 48, sy + sh - cy - 14, pros, cons, max_each=2)
    _footer_nav(c, n)


# ═════════════════════════════════════════════════════════════════════════
# P4 · FUTURO + SMART MONEY
# ═════════════════════════════════════════════════════════════════════════
def _medio_bloque(c, a, x, top, w, *, key, code, titulo, subtitulo, pills, rkey_verdict):
    r = _rep(a, key)
    s = _score(r)
    if s is not None:
        verdict, est = _verdict_generic(rkey_verdict, s)
    else:
        verdict, est = "Bloque sin datos", SIN_DATO()
    _mini_header(c, x, top, w, code, titulo, subtitulo, s, verdict, est)
    cy = top + 86
    if not _rep_ok(r):
        _aviso_bloque(c, x, cy, w, CONTENT_BOTTOM - cy, _AVISO_BLOQUE)
        return
    cy = _pills_grid(c, x, cy, w, pills, cols=2, h=84, gap=12)
    by = cy + 16
    bh = 184
    ccy = _card(c, x, by, w, bh, title="PILARES DEL BLOQUE", subtitle="Sub-calificaciones · 0–100")
    _native_bars(c, x + 24, ccy + 6, w - 48, _pilares(a, key), row_h=30, name_size=13,
                 score_size=16, ticks=False)
    sy = by + bh + 16
    sh = CONTENT_BOTTOM - sy
    scy = _card(c, x, sy, w, sh, title="SEÑALES DEL ANÁLISIS")
    pros, cons = _pros(r, 2), _cons(r, 2)
    if not pros and not cons:
        pros = [_conclusion(key, s)]
    _signals(c, x + 24, scy + 2, w - 48, sy + sh - scy - 14, pros, cons, max_each=2, size=13)


def _pagina_4_futuro_smart(c, a):
    n = 4
    _bookmark(c, n)
    _header(c, a, n)
    sec = SECCIONES[3]
    body_top = _section_header(c, sec, right_chip="DOS BLOQUES · CALIDAD Y RESPALDO")
    x, w = MARGIN_X, CONTENT_W
    hw = (w - 36) / 2
    _medio_bloque(c, a, x, body_top, hw, key="future", code="FU", titulo="FUTURO",
                  subtitulo="La ventaja competitiva y el recorrido que le queda",
                  pills=_pills_future(a), rkey_verdict="future")
    _medio_bloque(c, a, x + hw + 36, body_top, hw, key="institutional", code="SM",
                  titulo="SMART MONEY",
                  subtitulo="Qué hacen los grandes fondos y los directivos",
                  pills=_pills_institutional(a), rkey_verdict="institutional")
    _footer_nav(c, n)


# ═════════════════════════════════════════════════════════════════════════
# P5 · CONTEXTO DEL MERCADO
# ═════════════════════════════════════════════════════════════════════════
def _columna_contexto(c, a, x, top, w, *, key, code, titulo, subtitulo, pills,
                      texto_titulo, texto):
    r = _rep(a, key)
    s = _score(r)
    verdict, est = _verdict_generic(key, s) if s is not None else ("Bloque sin datos", SIN_DATO())
    _mini_header(c, x, top, w, code, titulo, subtitulo, s, verdict, est)
    cy = top + 86
    if not _rep_ok(r):
        _aviso_bloque(c, x, cy, w, CONTENT_BOTTOM - cy, _AVISO_BLOQUE)
        return
    cy = _pills_grid(c, x, cy, w, pills, cols=2, h=84, gap=12)
    ty = cy + 16
    th = 168
    _text_card(c, x, ty, w, th, texto_titulo, texto, size=12.5)
    sy = ty + th + 16
    sh = CONTENT_BOTTOM - sy
    scy = _card(c, x, sy, w, sh, title="SEÑALES DEL ANÁLISIS")
    pros, cons = _pros(r, 1), _cons(r, 1)
    if not pros and not cons:
        pros = [_conclusion(key, s)]
    _signals(c, x + 24, scy + 2, w - 48, sy + sh - scy - 14, pros, cons, max_each=1, size=12.5)


def _pagina_5_contexto(c, a):
    n = 5
    _bookmark(c, n)
    _header(c, a, n)
    sec = SECCIONES[4]
    body_top = _section_header(c, sec, right_chip="TRES BLOQUES · EL ENTORNO DE LA ACCIÓN")
    x, w = MARGIN_X, CONTENT_W
    cw = (w - 2 * 36) / 3
    cat = _rep(a, "catalysts")
    _columna_contexto(c, a, x, body_top, cw, key="catalysts", code="CT", titulo="CATALIZADORES",
                      subtitulo="Eventos que pueden mover el precio", pills=_pills_catalysts(a),
                      texto_titulo="EL EVENTO CLAVE",
                      texto=_limpiar(_km(cat).get("key_upcoming_event") or
                                     _rd(cat).get("top_catalyst") or ""))
    mac = _rep(a, "macro")
    _columna_contexto(c, a, x + cw + 36, body_top, cw, key="macro", code="MC", titulo="MACRO",
                      subtitulo="Cómo ayuda o estorba el entorno económico", pills=_pills_macro(a),
                      texto_titulo="LECTURA DEL ENTORNO",
                      texto=_limpiar(_rd(mac).get("macro_verdict") or ""))
    sen = _rep(a, "sentiment")
    _columna_contexto(c, a, x + 2 * (cw + 36), body_top, cw, key="sentiment", code="SN",
                      titulo="SENTIMIENTO", subtitulo="Qué dicen el mercado y las noticias",
                      pills=_pills_sentiment(a), texto_titulo="LA NARRATIVA DOMINANTE",
                      texto=_limpiar(_rd(sen).get("dominant_narrative") or ""))
    _footer_nav(c, n)


# ═════════════════════════════════════════════════════════════════════════
# P6 · RIESGO Y RECORRIDO DEL PRECIO
# ═════════════════════════════════════════════════════════════════════════
def _pagina_6_riesgo(c, a):
    n = 6
    _bookmark(c, n)
    _header(c, a, n)
    sec = SECCIONES[5]
    r = _rep(a, "risk")
    s = _score(r)
    verdict, est = _verdict_asymmetry(getattr(a, "asymmetry_direction", None),
                                      getattr(a, "asymmetry_strength", None))
    body_top = _section_header(c, sec, score=s, verdict=verdict, estado=est)
    x, w = MARGIN_X, CONTENT_W
    left_w, gap = 1180, 16

    ch = 412
    cy = _card(c, x, body_top, left_w, ch, title="RECORRIDO DEL PRECIO",
               subtitle="Dónde está hoy, hasta dónde podría caer y hasta dónde podría llegar")
    ok = _draw_fig(c, _build_price_journey_chart(a), x + 16, cy + 2, left_w - 32,
                   body_top + ch - cy - 16, px_w=1700, px_h=int(1700 * (ch - 70) / (left_w - 32)))
    if not ok:
        _text(c, "Sin histórico de precios suficiente esta vez.", x + 24, cy + 40,
              font=FONT_REG, size=14, color=TEXT_DIM)

    p = _precios(a)
    ty = body_top + ch + gap
    th = 150
    tw3 = (left_w - 2 * gap) / 3
    tiles = [
        ("PRECIO ACTUAL", ORANGE, _money(p["actual"]), "lo que costaba al cierre del análisis"),
        ("PRECIO MÍNIMO · NIVEL DE PROTECCIÓN", RED, _money(p["stop"]),
         f"pérdida prevista si se llega: {p['down']:+.1f}%" if p["down"] is not None else "nivel de salida defensiva"),
        ("PRECIO POTENCIAL · OBJETIVO", GREEN, _money(p["target"]),
         f"recorrido posible: {p['up']:+.1f}%" if p["up"] is not None else "precio objetivo del análisis"),
    ]
    for i, (lab, colr, val, sub) in enumerate(tiles):
        tx = x + i * (tw3 + gap)
        _box(c, tx, ty, tw3, th, r=12, fill=BG_CARD, stroke=_border_of(colr))
        c.setFillColor(colr)
        c.roundRect(tx, _y(ty + 4), tw3, 4, 2, stroke=0, fill=1)
        _dot(c, tx + 26, ty + 38, 5.5, colr, glow=True)
        _text(c, lab, tx + 42, ty + 42, font=FONT_DISPLAY, size=11, color=TEXT_LO, tracking=1.2)
        _text(c, val, tx + 26, ty + 100, font=FONT_DISPLAY_XL, size=40, color=_num_of(colr))
        _text(c, sub, tx + 26, ty + 128, font=FONT_REG, size=12.5, color=TEXT_DIM)

    ly = ty + th + gap
    lh_ = CONTENT_BOTTOM - ly
    _box(c, x, ly, left_w, lh_, r=12, fill=BG_CARD2, stroke=BORDER)
    plan = _plan_posicion(a)
    rr_row = plan[0]
    _dot(c, x + 26, ly + lh_ / 2, 7, rr_row[2].color, glow=True)
    _text(c, "LECTURA RÁPIDA", x + 46, ly + 28, font=FONT_DISPLAY, size=10.5, color=TEXT_LO, tracking=1.4)
    lectura = (f"{rr_row[3]}. " if rr_row[3] else "") + \
        ("Lo que puedes ganar supera lo que arriesgas: la relación juega a favor."
         if rr_row[2].nivel == "bien" else
         "Premio y riesgo van bastante parejos: el precio de entrada importa mucho."
         if rr_row[2].nivel == "regular" else
         "Hoy arriesgas más de lo que puedes ganar: la relación juega en contra."
         if rr_row[2].nivel == "mal" else "No pudimos medir la relación esta vez.")
    _text(c, _fit_text(c, lectura, FONT_REG, 14, left_w - 80), x + 46, ly + 52,
          font=FONT_REG, size=14, color=TEXT_MD)

    rx = x + left_w + 18
    rw = w - left_w - 18
    ph = 396
    cy = _card(c, rx, body_top, rw, ph, title="PLAN DE LA POSICIÓN",
               subtitle="Cuánto arriesgar, cuánto esperar y cuánto invertir")
    row_h = (body_top + ph - 14 - (cy + 6)) / len(plan)
    ry = cy + 6
    for i, (lab, val, estado, reading) in enumerate(plan):
        _text(c, lab, rx + 24, ry + 22, font=FONT_REG, size=12.5, color=TEXT_LO)
        _estado_chip(c, rx + rw - 24, ry + 22, estado, size=10)
        _text(c, val, rx + 24, ry + 48, font=FONT_DISPLAY_XL, size=20,
              color=TEXT_HI if estado.nivel != "sin" else TEXT_DIM)
        if reading:
            vw = c.stringWidth(val, FONT_DISPLAY_XL, 20)
            _text(c, _fit_text(c, reading, FONT_REG, 11, rw - 48 - vw - 16), rx + rw - 24,
                  ry + 48, font=FONT_REG, size=11, color=TEXT_DIM, anchor="right")
        if i < len(plan) - 1:
            c.setStrokeColor(BORDER)
            c.setLineWidth(0.8)
            c.line(rx + 24, _y(ry + row_h - 4), rx + rw - 24, _y(ry + row_h - 4))
        ry += row_h

    sy = body_top + ph + gap
    sh = CONTENT_BOTTOM - sy
    cy = _card(c, rx, sy, rw, sh, title="POR QUÉ AHÍ EL NIVEL DE PROTECCIÓN")
    razon = _limpiar(_rd(r).get("stop_rationale") or "")
    if razon:
        cy = _wrap(c, razon, rx + 24, cy + 18, rw - 48, font=FONT_REG, size=13, color=TEXT_MD,
                   line_height=1.36, max_lines=4)
    else:
        _text(c, "Sin explicación disponible esta vez.", rx + 24, cy + 22, font=FONT_REG,
              size=13, color=TEXT_DIM)
        cy += 40
    pros, cons = _pros(r, 1), _cons(r, 1)
    _signals(c, rx + 24, cy + 10, rw - 48, sy + sh - cy - 24, pros, cons, max_each=1, size=12.5)
    _footer_nav(c, n)


# ═════════════════════════════════════════════════════════════════════════
# P7 · CONCLUSIÓN Y CLUB DLP
# ═════════════════════════════════════════════════════════════════════════
def _lista_card(c, x, top, w, h, title, items, color, icon, *, size=14.5, max_lines=3):
    cy = _card(c, x, top, w, h, title=title, accent=color)
    cy += 6
    lh = size * 1.38
    bottom = top + h - 16
    items = [i for i in items if i]
    if not items:
        _text(c, "Sin datos esta vez.", x + 28, cy + 22, font=FONT_REG, size=size, color=TEXT_DIM)
        return
    for it in items:
        lines = _wrap_lines(c, it, w - 80, font=FONT_REG, size=size, max_lines=max_lines)
        block = lh * len(lines)
        if cy + block > bottom:
            break
        icon(c, x + 38, cy + size * 0.36 + 2, 9.5, color)
        _wrap(c, it, x + 58, cy + size * 0.95, w - 80, font=FONT_REG, size=size,
              color=TEXT_MD, line_height=1.38, max_lines=max_lines)
        cy += block + 12


def _cta(c, x, top, w, h):
    _box(c, x, top, w, h, r=18, fill=BG_CTA, stroke=ORANGE_DK, stroke_w=1.5)
    c.setStrokeColor(GOLD)
    c.setStrokeAlpha(0.35)
    c.setLineWidth(1)
    c.roundRect(x + 5, _y(top + h - 5), w - 10, h - 10, 14, stroke=1, fill=0)
    c.setStrokeAlpha(1)
    # Franja superior degradada oro → transparente
    steps = 80
    seg = (w - 36) / steps
    for i in range(steps):
        c.setFillColor(GOLD)
        c.setFillAlpha(0.55 * (1 - i / steps))
        c.rect(x + 18 + i * seg, _y(top + 9), seg + 0.6, 2.2, stroke=0, fill=1)
    c.setFillAlpha(1)

    # Logo
    lx, lw = x + 36, 300
    if LOGO_PATH is not None:
        img = _styled_logo_png(LOGO_PATH, max_dim_px=900, corner_radius_pct=0.12,
                               glow_color=(255, 200, 110), glow_blur=36,
                               glow_intensity=0.6, pad_px=70)
        if img is not None:
            c.drawImage(img, lx, _y(top + h - 22), width=lw, height=h - 44,
                        preserveAspectRatio=True, anchor="c", mask="auto")
    # QR sobre tile crema
    qs = 168
    qx = x + w - 36 - qs
    qy = top + 26
    _box(c, qx, qy, qs, qs, r=14, fill=CREAM)
    qr = _qr_image(CLUB_DLP_URL, size_px=qs * 3)
    if qr is not None:
        c.drawImage(qr, qx + 8, _y(qy + qs - 8), width=qs - 16, height=qs - 16, mask="auto")
    c.linkURL(CLUB_DLP_URL, (qx, _y(qy + qs), qx + qs, _y(qy)), relative=0, thickness=0)
    _text(c, "escanea para entrar", qx + qs / 2, top + h - 16, font=FONT_REG, size=10.5,
          color=TEXT_DIM, anchor="center")

    # Botón
    bw, bh = 300, 52
    bx = qx - 36 - bw
    by = top + h - 36 - bh
    _box(c, bx, by, bw, bh, r=12, fill=ORANGE)
    _text(c, "ÚNETE AL CLUB DLP", bx + 26, by + bh / 2 + 5.5, font=FONT_DISPLAY_XL, size=15,
          color=INK, tracking=1.2)
    _icon_arrow_right(c, bx + bw - 58, by + bh / 2, 28, INK, lw=2.4)
    c.linkURL(CLUB_DLP_URL, (bx, _y(by + bh), bx + bw, _y(by)), relative=0, thickness=0)
    _text(c, CLUB_DLP_DOMAIN, bx + bw, by - 14, font=FONT_BOLD, size=13, color=GOLD, anchor="right")
    _text(c, CLUB_DLP_HANDLE, bx + bw, by - 34, font=FONT_REG, size=12.5, color=TEXT_LO, anchor="right")

    # Titular + beneficios
    tx = lx + lw + 40
    tw_ = bx - 40 - tx
    _text(c, _fit_text(c, "ANALIZA ASÍ CUALQUIER ACCIÓN", FONT_DISPLAY_XL, 30, tw_), tx, top + 66,
          font=FONT_DISPLAY_XL, size=30, color=TEXT_HI)
    _text(c, "Informes como este, con los mismos nueve analistas de IA, en minutos.",
          tx, top + 94, font=FONT_REG, size=14, color=TEXT_LO)
    beneficios = ["Cualquier acción del mercado, analizada a fondo y explicada en español claro",
                  "Calificación, niveles de protección y precio objetivo en cada informe",
                  "Una comunidad que invierte a largo plazo, sin promesas ni humo"]
    cy = top + 130
    for b in beneficios:
        _icon_check(c, tx + 10, cy - 5, 9.5, GOLD)
        _text(c, _fit_text(c, b, FONT_REG, 14.5, tw_ - 36), tx + 30, cy, font=FONT_REG,
              size=14.5, color=TEXT_MD)
        cy += 30


def _pagina_7_conclusion(c, a):
    n = 7
    _bookmark(c, n)
    _header(c, a, n)
    sec = SECCIONES[6]
    body_top = _section_header(c, sec, right_chip=f"HORIZONTE · {_horizonte(a).upper()}")
    x, w = MARGIN_X, CONTENT_W
    hw = (w - 36) / 2
    fh = 296
    fort = [_limpiar(t) for t in (getattr(a, "key_strengths", None) or []) if t][:3]
    ries = [_limpiar(t) for t in (getattr(a, "key_risks", None) or []) if t][:3]
    _lista_card(c, x, body_top, hw, fh, "LO QUE PESA A FAVOR", fort, GREEN, _icon_check)
    _lista_card(c, x + hw + 36, body_top, hw, fh, "LO QUE PESA EN CONTRA", ries, RED, _icon_minus)

    ey = body_top + fh + 16
    eh = 112
    _text_card(c, x, ey, hw, eh, "CÓMO ENTRAR, SEGÚN EL ANÁLISIS",
               _limpiar(getattr(a, "entry_strategy", "") or ""), size=13, max_lines=3)
    _text_card(c, x + hw + 36, ey, hw, eh, "CUÁNDO SALIR, SEGÚN EL ANÁLISIS",
               _limpiar(getattr(a, "exit_strategy", "") or ""), size=13, max_lines=3)

    cy = ey + eh + 16
    _cta(c, x, cy, w, CONTENT_BOTTOM - cy)
    _footer_nav(c, n)


PAGINAS = [
    _pagina_1_veredicto, _pagina_2_fundamentales, _pagina_3_tecnico,
    _pagina_4_futuro_smart, _pagina_5_contexto, _pagina_6_riesgo, _pagina_7_conclusion,
]
