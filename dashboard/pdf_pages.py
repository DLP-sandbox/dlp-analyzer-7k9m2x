"""
dashboard/pdf_pages.py — Las 3 páginas del Informe DLP.

Diseñado para que un principiante lo lea UNA vez y lo entienda:
  1. Veredicto   — quién es la empresa, el puntaje, dos gráficas y «en pocas palabras»
  2. El negocio  — 3 datos con semáforo y frase sin cifras, los pilares y la lectura
  3. El momento  — 3 datos, el recorrido del precio, la lectura y el Club DLP

Cada página comparte cabecera, pie (disclaimer · paginación) y la barra de
navegación clicable. Cero llamadas a Anthropic: solo lee el StockAnalysis y dibuja.
"""
from dashboard.pdf_theme import (
    PAGE_W, MARGIN_X, CONTENT_W, HEADER_RULE_TOP, CONTENT_TOP, CONTENT_BOTTOM,
    NAV_TOP, NAV_H, FOOT_BASE,
    BG_CARD, BG_CARD2, BG_CTA, ORANGE, ORANGE_DK, GOLD, GREEN, RED,
    TEXT_HI, TEXT_MD, TEXT_LO, TEXT_DIM, BORDER, INK, CREAM,
    CLUB_DLP_URL, CLUB_DLP_DOMAIN, CLUB_DLP_HANDLE, DISCLAIMER,
    FONT_REG, FONT_BOLD, FONT_DISPLAY, FONT_DISPLAY_XL,
    _y, _fill_bg, _box, _text, _text_w, _fit_text, _wrap, _wrap_lines,
    _score_color, _rec_palette, _num_of, _border_of,
    SIN_DATO, Estado,
    _dot, _icon_diamond, _icon_check, _icon_arrow_right,
    _card, _chip, _native_bars, _metric_tile, _aviso_bloque,
)
from dashboard.pdf_rules import (
    SECCIONES, _rep, _rep_ok, _km, _score, _pilares, _to_float, _es_sector, _negocio,
    _verdict_stability, _verdict_asymmetry, _fundamentales_specs, _momento_specs,
    _en_pocas_palabras, _enum_es, _precios, _fecha_es,
)
from dashboard.pdf_charts import LOGO_PATH, _styled_logo_png, _logo_directo
from dashboard.pdf_vector import dibujar_medidor, dibujar_radar, dibujar_precio, dibujar_qr

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
    _icon_diamond(c, MARGIN_X + 7, 84, 6.5, ORANGE)
    _text(c, "DLP MARKET ANALYZER", MARGIN_X + 22, 89, font=FONT_DISPLAY, size=13,
          color=ORANGE, tracking=1.8)
    tk = str(getattr(a, "ticker", "") or "")
    x_tk = MARGIN_X + 300
    _text(c, tk, x_tk, 92, font=FONT_DISPLAY_XL, size=24, color=TEXT_HI)
    tw = c.stringWidth(tk, FONT_DISPLAY_XL, 24)
    name = _fit_text(c, getattr(a, "company_name", "") or "", FONT_REG, 14, 520)
    _text(c, name, x_tk + tw + 14, 92, font=FONT_REG, size=14, color=TEXT_LO)
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
    c.setStrokeColor(BORDER)
    c.setLineWidth(1)
    c.line(MARGIN_X, _y(HEADER_RULE_TOP), PAGE_W - MARGIN_X, _y(HEADER_RULE_TOP))


def _footer_nav(c, n: int):
    size, pad, gap, h = 11.5, 18, 12, 36
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
    _text(c, f"{CLUB_DLP_DOMAIN}  ·  pulsa una sección para ir a ella", MARGIN_X, FOOT_BASE,
          font=FONT_REG, size=10, color=TEXT_DIM)
    _text(c, DISCLAIMER, PAGE_W / 2, FOOT_BASE, font=FONT_REG, size=9.5, color=TEXT_DIM,
          anchor="center")
    _text(c, f"{n} / {TOTAL}", PAGE_W - MARGIN_X, FOOT_BASE, font=FONT_DISPLAY, size=11,
          color=TEXT_LO, anchor="right", tracking=1.0)


def _section_header(c, sec: dict, *, score=None, verdict=None, estado: Estado = None,
                    top=CONTENT_TOP, h=92) -> float:
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
    if verdict and estado is not None:
        tw = c.stringWidth(verdict, FONT_BOLD, 16)
        _text(c, verdict, right, top + 52, font=FONT_BOLD, size=16, color=TEXT_HI, anchor="right")
        _dot(c, right - tw - 16, top + 52 - 16 * 0.36, 7, estado.color, glow=True)
        if estado.palabra:
            _text(c, estado.palabra, right, top + 72, font=FONT_DISPLAY, size=10.5,
                  color=estado.color, anchor="right", tracking=1.2)
    return top + h + 18


def _pocas_palabras_card(c, x, top, w, h, texto, *, title="EN POCAS PALABRAS",
                         size=20, chips=None, nota=None):
    """La lectura en llano: una frase grande, sin cifras, que se entiende a la primera."""
    _box(c, x, top, w, h, r=14, fill=BG_CARD, stroke=_border_of(ORANGE))
    c.setFillColor(ORANGE)
    c.roundRect(x, _y(top + h), 5, h, 2.5, stroke=0, fill=1)
    _text(c, title, x + 30, top + 34, font=FONT_DISPLAY, size=12.5, color=ORANGE, tracking=1.4)
    cy = top + 44
    if chips:
        cx = x + 30
        for label, value, color in chips:
            cw = _chip(c, cx, cy + 12, f"{label}: {value}", fill=BG_CARD2, color=color or TEXT_MD,
                       h=28, size=11, pad=12, tracking=0.6)
            cx += cw + 10
        cy += 52
    lh = size * 1.42
    avail = top + h - 26 - (cy + size)
    max_lines = max(2, int(avail // lh) + 1)
    lines = _wrap_lines(c, texto, w - 60, font=FONT_REG, size=size, max_lines=max_lines)
    # Si cabe, se centra verticalmente en el espacio libre
    block = lh * (len(lines) - 1) + size
    free = top + h - (46 if nota else 26) - cy
    start = cy + max(size, (free - block) / 2 + size * 0.8)
    c.setFont(FONT_REG, size)
    c.setFillColor(TEXT_HI)
    yy = start
    for ln in lines:
        c.drawString(x + 30, _y(yy), ln)
        yy += lh
    if nota:
        _text(c, _fit_text(c, nota, FONT_REG, 12, w - 60), x + 30, top + h - 24,
              font=FONT_REG, size=12, color=TEXT_DIM)


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
    pocas = _en_pocas_palabras(a)

    # ── Quién es ───────────────────────────────────────────────────────
    top, h = CONTENT_TOP, 150
    _box(c, x, top, w, h, r=14, fill=BG_CARD, stroke=_border_of(ORANGE))
    c.setFillColor(ORANGE)
    c.roundRect(x, _y(top + h), 5, h, 2.5, stroke=0, fill=1)
    tk = str(getattr(a, "ticker", "") or "")
    _text(c, tk, x + 40, top + 88, font=FONT_DISPLAY_XL, size=68, color=ORANGE)
    tkw = c.stringWidth(tk, FONT_DISPLAY_XL, 68)
    name = _fit_text(c, getattr(a, "company_name", "") or "", FONT_BOLD, 24, 760)
    _text(c, name, x + 40 + tkw + 24, top + 88, font=FONT_BOLD, size=24, color=TEXT_HI)
    sector_txt = _es_sector(getattr(a, "sector", ""))
    negocio = _negocio(getattr(a, "sector", ""))
    if negocio and sector_txt and negocio.strip().lower() == sector_txt.strip().lower():
        negocio = ""
    partes = [p for p in (sector_txt, negocio, "Pensado para el largo plazo") if p]
    _text(c, _fit_text(c, "   ·   ".join(partes), FONT_REG, 14, 1000), x + 42, top + 122,
          font=FONT_REG, size=14, color=TEXT_LO)
    right = x + w - 40
    _text(c, f"{sc:.1f}" if sc is not None else "—", right, top + 82, font=FONT_DISPLAY_XL,
          size=76, color=_num_of(col), anchor="right")
    _text(c, "PUNTAJE GLOBAL  /  100", right, top + 108, font=FONT_DISPLAY, size=11.5,
          color=TEXT_LO, anchor="right", tracking=1.6)
    cx = right
    fill, tcol = _rec_palette(getattr(a, "recommendation", "") or "")
    cx -= _chip(c, cx, top + 116, _rec_txt(a), fill=fill, color=tcol, h=28, size=11.5, anchor="right") + 10
    conv = _CONV_ES.get(str(getattr(a, "conviction_level", "") or "").upper())
    if conv:
        cx -= _chip(c, cx, top + 116, f"CONVICCIÓN {conv}", fill=BG_CARD2, color=TEXT_MD,
                    h=28, size=11, anchor="right") + 10
    if getattr(a, "is_compound_machine", False):
        _chip(c, cx, top + 116, "COMPOUNDER", fill=GOLD, color=INK, h=28, size=11, anchor="right")

    # ── Dos gráficas + en pocas palabras ───────────────────────────────
    top2 = top + h + 18
    h2 = CONTENT_BOTTOM - top2
    gw, gap = 520, 18
    vw = w - 2 * gw - 2 * gap
    cy = _card(c, x, top2, gw, h2, title="PUNTAJE DLP",
               subtitle=f"Calificación global · {_rec_txt(a)}")
    dibujar_medidor(c, x + 20, cy + 30, gw - 40, top2 + h2 - cy - 50, sc, _rec_txt(a))
    x2 = x + gw + gap
    cy = _card(c, x2, top2, gw, h2, title="PERFIL DE CALIDAD",
               subtitle="Cinco dimensiones · cuanto más lleno, mejor")
    dibujar_radar(c, x2 + 20, cy + 16, gw - 40, top2 + h2 - cy - 36,
                  getattr(a, "snowflake", None) or {})
    x3 = x2 + gw + gap
    _pocas_palabras_card(c, x3, top2, vw, h2, pocas["global"], size=25,
                         nota="Página 2: ¿es un buen negocio?   ·   Página 3: ¿es buen momento?")
    _footer_nav(c, n)


# ═════════════════════════════════════════════════════════════════════════
# P2 · ¿ES UN BUEN NEGOCIO?
# ═════════════════════════════════════════════════════════════════════════
def _pagina_2_negocio(c, a):
    n = 2
    _bookmark(c, n)
    _header(c, a, n)
    sec = SECCIONES[1]
    r = _rep(a, "fundamentals")
    s = _score(r)
    verdict, est = _verdict_stability(s) if s is not None else ("Bloque sin datos", SIN_DATO())
    body_top = _section_header(c, sec, score=s, verdict=verdict, estado=est)
    x, w = MARGIN_X, CONTENT_W
    if not _rep_ok(r):
        _aviso_bloque(c, x, body_top, w, CONTENT_BOTTOM - body_top, _AVISO_BLOQUE)
        _footer_nav(c, n)
        return
    pocas = _en_pocas_palabras(a)
    specs = _fundamentales_specs(a)
    tres = [specs[0], specs[1], specs[4]]          # crece · gana · debe
    gap = 16
    tw3 = (w - 2 * gap) / 3
    th = 300
    for i, spec in enumerate(tres):
        _metric_tile(c, x + i * (tw3 + gap), body_top, tw3, th, spec)

    top3 = body_top + th + gap
    h3 = CONTENT_BOTTOM - top3
    lw = 860
    cy = _card(c, x, top3, lw, h3, title="LOS PILARES DEL NEGOCIO",
               subtitle="Calidad, crecimiento, precio y solidez · de cero a cien")
    _native_bars(c, x + 24, cy + 16, lw - 48, _pilares(a, "fundamentals"),
                 row_h=(top3 + h3 - 30 - 22 - (cy + 16)) / 4, name_size=15, score_size=20)
    km = _km(_rep(a, "future"))
    moat = str(km.get("moat_strength") or "").lower()
    chips = []
    if moat:
        color = GREEN if "wide" in moat else ORANGE if "narrow" in moat else RED
        chips.append(("Ventaja competitiva", _enum_es(moat), color))
    _pocas_palabras_card(c, x + lw + gap, top3, w - lw - gap, h3, pocas["negocio"],
                         size=19, chips=chips)
    _footer_nav(c, n)


# ═════════════════════════════════════════════════════════════════════════
# P3 · ¿ES BUEN MOMENTO?  + Club DLP
# ═════════════════════════════════════════════════════════════════════════
def _cta(c, x, top, w, h):
    _box(c, x, top, w, h, r=16, fill=BG_CTA, stroke=ORANGE_DK, stroke_w=1.5)
    c.setStrokeColor(GOLD)
    c.setStrokeAlpha(0.35)
    c.setLineWidth(1)
    c.roundRect(x + 5, _y(top + h - 5), w - 10, h - 10, 12, stroke=1, fill=0)
    c.setStrokeAlpha(1)
    steps, seg = 80, (w - 36) / 80
    for i in range(steps):
        c.setFillColor(GOLD)
        c.setFillAlpha(0.55 * (1 - i / steps))
        c.rect(x + 18 + i * seg, _y(top + 8), seg + 0.6, 2, stroke=0, fill=1)
    c.setFillAlpha(1)

    lw = int((h - 32) * 1.78)
    lx = x + 30
    if LOGO_PATH is not None:
        img = _styled_logo_png(LOGO_PATH, max_dim_px=900, corner_radius_pct=0.12,
                               glow_color=(255, 200, 110), glow_blur=36,
                               glow_intensity=0.6, pad_px=70) or _logo_directo(LOGO_PATH)
        if img is not None:
            c.drawImage(img, lx, _y(top + h - 16), width=lw, height=h - 32,
                        preserveAspectRatio=True, anchor="c", mask="auto")
    qs = h - 40
    qx = x + w - 30 - qs
    qy = top + 20
    if not dibujar_qr(c, CLUB_DLP_URL, qx, qy, qs, radio=12):
        _box(c, qx, qy, qs, qs, r=12, fill=CREAM)
    c.linkURL(CLUB_DLP_URL, (qx, _y(qy + qs), qx + qs, _y(qy)), relative=0, thickness=0)

    bw, bh = 280, 46
    bx = qx - 30 - bw
    by = top + h / 2 - bh / 2 + 4
    _box(c, bx, by, bw, bh, r=11, fill=ORANGE)
    _text(c, "ÚNETE AL CLUB DLP", bx + 24, by + bh / 2 + 5, font=FONT_DISPLAY_XL, size=14,
          color=INK, tracking=1.2)
    _icon_arrow_right(c, bx + bw - 54, by + bh / 2, 26, INK, lw=2.3)
    c.linkURL(CLUB_DLP_URL, (bx, _y(by + bh), bx + bw, _y(by)), relative=0, thickness=0)
    _text(c, CLUB_DLP_DOMAIN, bx + bw, by - 12, font=FONT_BOLD, size=12, color=GOLD, anchor="right")
    _text(c, CLUB_DLP_HANDLE, bx + bw, by + bh + 24, font=FONT_REG, size=11.5, color=TEXT_LO,
          anchor="right")

    tx = lx + lw + 34
    tw_ = bx - 34 - tx
    _text(c, _fit_text(c, "ANALIZA ASÍ CUALQUIER ACCIÓN", FONT_DISPLAY_XL, 26, tw_), tx, top + 52,
          font=FONT_DISPLAY_XL, size=26, color=TEXT_HI)
    _text(c, _fit_text(c, "Informes como este, con los mismos nueve analistas de IA, en minutos.",
                       FONT_REG, 13.5, tw_), tx, top + 78, font=FONT_REG, size=13.5, color=TEXT_LO)
    cy = top + 106
    for b in ("Cualquier acción, analizada a fondo y explicada en español claro",
              "Una comunidad que invierte a largo plazo, sin promesas ni humo"):
        _icon_check(c, tx + 9, cy - 5, 8.5, GOLD)
        _text(c, _fit_text(c, b, FONT_REG, 13, tw_ - 30), tx + 26, cy, font=FONT_REG, size=13,
              color=TEXT_MD)
        cy += 24


def _pagina_3_momento(c, a):
    n = 3
    _bookmark(c, n)
    _header(c, a, n)
    sec = SECCIONES[2]
    r = _rep(a, "risk")
    s = _score(r)
    verdict, est = _verdict_asymmetry(getattr(a, "asymmetry_direction", None),
                                      getattr(a, "asymmetry_strength", None))
    body_top = _section_header(c, sec, score=s, verdict=verdict, estado=est)
    x, w = MARGIN_X, CONTENT_W
    pocas = _en_pocas_palabras(a)
    gap = 16
    tw3 = (w - 2 * gap) / 3
    th = 228
    for i, spec in enumerate(_momento_specs(a)):
        _metric_tile(c, x + i * (tw3 + gap), body_top, tw3, th, spec, compact=True)

    cta_h = 140
    top3 = body_top + th + gap
    h3 = CONTENT_BOTTOM - cta_h - gap - top3
    lw = 1180
    cy = _card(c, x, top3, lw, h3, title="EL RECORRIDO DEL PRECIO",
               subtitle="Dónde está hoy, hasta dónde podría caer y hasta dónde podría llegar")
    p = _precios(a)
    ok = dibujar_precio(c, x + 16, cy + 2, lw - 32, top3 + h3 - cy - 14, a,
                        niveles=[(p["stop"], "Mínimo", RED), (p["actual"], "Actual", ORANGE),
                                 (p["target"], "Potencial", GREEN)])
    if not ok:
        _text(c, "Sin histórico de precios suficiente esta vez.", x + 24, cy + 40,
              font=FONT_REG, size=14, color=TEXT_DIM)
    _pocas_palabras_card(c, x + lw + gap, top3, w - lw - gap, h3, pocas["momento"], size=19)

    _cta(c, x, CONTENT_BOTTOM - cta_h, w, cta_h)
    _footer_nav(c, n)


PAGINAS = [_pagina_1_veredicto, _pagina_2_negocio, _pagina_3_momento]
