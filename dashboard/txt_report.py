"""
Informe del análisis en TEXTO PLANO (.txt) — el gemelo ligero del PDF.

Objetivo: un solo archivo, sin formato ni imágenes, que contenga TODO lo que
la app muestra de una acción (los 9 agentes al completo + los datos de mercado
verificados en el momento de la descarga), escrito de forma cruda y ordenada
para que una IA lo lea entero, rápido y barato.

Garantías (idénticas en espíritu a las del PDF):
  · CERO llamadas a Anthropic — solo formatea datos que ya existen.
  · NUNCA lanza: cada bloque va protegido; si un dato falta, se omite el
    bloque y el resto del informe se genera igual.
  · No menciona proveedores de datos (blindaje de fuentes de la app).
  · No toca ni modifica el objeto `analysis` — solo lee.

El diccionario `live` (opcional) lo arma el dashboard con sus helpers ya
cacheados, así el informe no dispara descargas nuevas por su cuenta.
"""
from datetime import datetime
from typing import Any, Optional

SEP_H = "=" * 78
SEP_L = "-" * 78

# Nombre en español de cada sección/agente, en el mismo orden en que la app las
# presenta (barra de secciones → Overview, Técnico, Fundamentales, Futuro,
# Smart Money, Contexto del Mercado (catalizadores+macro+sentimiento), Riesgo).
AGENT_ORDER = [
    ("technical",     "TÉCNICO — tendencia, momentum y niveles"),
    ("fundamentals",  "FUNDAMENTALES — negocio, márgenes y valoración"),
    ("future",        "FUTURO — ventaja competitiva y recorrido a largo plazo"),
    ("institutional", "SMART MONEY — institucionales, directivos y posiciones cortas"),
    ("catalysts",     "CATALIZADORES — resultados y eventos que mueven el precio"),
    ("macro",         "MACRO — entorno de mercado y rotación sectorial"),
    ("sentiment",     "SENTIMIENTO — narrativa y noticias"),
    ("risk",          "RIESGO — entrada, stop, objetivo y tamaño de posición"),
]

CONV_ES = {"HIGH": "ALTA", "MEDIUM": "MEDIA", "LOW": "BAJA"}

# Claves de raw_data que NO se vuelcan: son series de precios completas (miles
# de números) que dispararían el tamaño del archivo sin aportar nada que no
# esté ya resumido en los indicadores y en la tabla de últimas sesiones.
RAW_SKIP = {"df_daily", "df_weekly", "df", "history", "closes", "prices"}

# Tope de caracteres por valor suelto volcado en crudo. Protege contra un campo
# gigante inesperado sin recortar nada de lo que se usa hoy.
MAX_VAL = 1200


# ── utilidades de formato ────────────────────────────────────────────────
def _s(v: Any, default: str = "—") -> str:
    """Valor legible en una línea. Nunca lanza."""
    try:
        if v is None:
            return default
        if isinstance(v, bool):
            return "sí" if v else "no"
        if isinstance(v, float):
            if v != v:                       # NaN
                return default
            return f"{v:,.2f}".rstrip("0").rstrip(".") if abs(v) < 1e6 else f"{v:,.0f}"
        if isinstance(v, int):
            return f"{v:,}"
        s = str(v).strip()
        if not s or s.lower() in ("nan", "none", "n/a"):
            return default
        return s[:MAX_VAL]
    except Exception:
        return default


def _num(v) -> Optional[float]:
    try:
        f = float(v)
        return None if f != f else f
    except Exception:
        return None


def _money(v) -> str:
    f = _num(v)
    return f"${f:,.2f}" if f is not None else "—"


def _big(v) -> str:
    """Cifras grandes en formato humano ($3.42 B / $912.5 M)."""
    f = _num(v)
    if f is None or f == 0:
        return "—"
    a = abs(f)
    for div, suf in ((1e12, " T"), (1e9, " B"), (1e6, " M"), (1e3, " K")):
        if a >= div:
            return f"${f / div:,.2f}{suf}"
    return f"${f:,.0f}"


def _pct(v, decimals: int = 1) -> str:
    f = _num(v)
    return f"{f:+.{decimals}f}%" if f is not None else "—"


def _kv(label: str, value: Any, width: int = 26) -> str:
    return f"{str(label)[:width].ljust(width)}: {_s(value)}"


def _title(n: int, text: str) -> list[str]:
    return ["", SEP_H, f"[{n}] {text}", SEP_H]


def _sub(text: str) -> list[str]:
    return ["", f"-- {text} " + "-" * max(0, 74 - len(text))]


def _bullets(items, prefix: str = "  · ") -> list[str]:
    out = []
    for it in (items or []):
        t = _s(it, "")
        if t:
            out.append(f"{prefix}{t}")
    return out or ["  (sin datos)"]


def _para(text, indent: str = "  ") -> list[str]:
    """Texto narrativo tal cual, respetando sus saltos de línea."""
    t = str(text or "").strip()
    if not t:
        return [f"{indent}(sin datos)"]
    return [f"{indent}{ln.strip()}" if ln.strip() else "" for ln in t.split("\n")]


def _dump_dict(d: dict, indent: str = "  ", width: int = 26) -> list[str]:
    """Vuelca un dict en crudo (clave: valor), aplanando un nivel de anidación.
    Omite vacíos y series pesadas. Pensado para que una IA lo lea directo."""
    out = []
    if not isinstance(d, dict):
        return out
    for k, v in d.items():
        if str(k).lower() in RAW_SKIP:
            continue
        if v is None or v == "" or v == [] or v == {}:
            continue
        if isinstance(v, dict):
            sub = _dump_dict(v, indent + "  ", width)
            if sub:
                out.append(f"{indent}{k}:")
                out.extend(sub)
        elif isinstance(v, (list, tuple)):
            vals = [x for x in v if x not in (None, "")]
            if not vals:
                continue
            if all(isinstance(x, (str, int, float, bool)) for x in vals):
                out.append(f"{indent}{str(k).ljust(width)}: " +
                           "; ".join(_s(x) for x in vals[:20]))
            else:
                out.append(f"{indent}{k}:")
                for x in vals[:12]:
                    if isinstance(x, dict):
                        pares = "; ".join(f"{kk}={_s(vv)}" for kk, vv in x.items()
                                          if vv not in (None, "", [], {}))
                        if pares:
                            out.append(f"{indent}  - {pares}")
                    else:
                        out.append(f"{indent}  - {_s(x)}")
        else:
            out.append(f"{indent}{str(k).ljust(width)}: {_s(v)}")
    return out


def _sector_es(sector) -> str:
    """Sector en español, igual que lo rotula la app. Si el mapeo no está
    disponible, devuelve el valor original — nunca lanza."""
    try:
        from data.industry_labels import sector_es
        return sector_es(sector) or _s(sector)
    except Exception:
        return _s(sector)


def _rec_es(rec) -> str:
    """Etiqueta de la recomendación tal y como la ve el usuario en la app."""
    try:
        from config.settings import rec_display
        return rec_display(rec) or _s(rec)
    except Exception:
        return _s(rec)


def _negocio(info: dict) -> str:
    """Frase corta en español de a qué se dedica la empresa (la misma que usa
    la app). Devuelve '' si no hay dato — la línea se queda con su guion."""
    try:
        from data.industry_labels import describe_business
        return describe_business((info or {}).get("industry"),
                                 (info or {}).get("sector")) or ""
    except Exception:
        return ""


def _fecha_es(iso: str) -> str:
    try:
        return datetime.fromisoformat(str(iso)).strftime("%d/%m/%Y %H:%M")
    except Exception:
        return str(iso or "—")[:16]


# ── construcción del informe ─────────────────────────────────────────────
def build_analysis_txt(analysis, live: Optional[dict] = None) -> str:
    """Devuelve el informe completo del análisis como texto plano.

    `analysis` es el StockAnalysis (o cualquier objeto con sus atributos).
    `live` es opcional: dict con los datos de mercado frescos que el dashboard
    ya tiene cacheados (info, indicators, rs, risk_levels, holders, events,
    earnings, news, macro, ohlcv). Si viene vacío, el informe se genera igual
    solo con lo guardado en el análisis.
    """
    live = live if isinstance(live, dict) else {}
    L: list[str] = []
    g = lambda attr, d=None: getattr(analysis, attr, d)   # noqa: E731

    info    = live.get("info") or {}
    ind     = live.get("indicators") or {}
    rlevels = live.get("risk_levels") or {}
    ahora   = datetime.now().strftime("%d/%m/%Y %H:%M")

    ticker = _s(g("ticker"), "—")
    precio_vivo = _num(info.get("current_price")) or _num(rlevels.get("current_price"))

    # ── Cabecera ────────────────────────────────────────────────────────
    L += [
        SEP_H,
        "DLP MARKET ANALYZER — INFORME COMPLETO EN TEXTO PLANO",
        SEP_H,
        _kv("Acción", f"{ticker} — {_s(g('company_name'))}"),
        _kv("Sector", _sector_es(g("sector") or (live.get("info") or {}).get("sector"))),
        _kv("Análisis generado el", _fecha_es(g("timestamp"))),
        _kv("Datos verificados el", f"{ahora} (releídos al descargar)"),
        _kv("Precio en la descarga", _money(precio_vivo)),
        "",
        "CÓMO USAR ESTE ARCHIVO",
        "  Contiene el 100% del análisis que muestra la app: todos los bloques",
        "  de análisis completos, todas sus métricas y los datos de mercado",
        "  verificados en el momento de la descarga. Está en texto plano y",
        "  ordenado por secciones numeradas para que una IA lo procese entero",
        "  de una sola lectura. Las métricas se listan con su nombre técnico",
        "  original (crudo) y su valor.",
        "",
        "ÍNDICE",
        "  [1] Veredicto global          [7]  Oportunidad detectada",
        "  [2] Niveles de operación      [8]  Indicadores técnicos en vivo",
        "  [3] Datos de mercado en vivo  [9]  Últimas sesiones (OHLCV)",
        "  [4] Puntuaciones y desglose   [10] Análisis detallado por bloque",
        "  [5] Tesis de inversión        [11] Datos vivos complementarios",
        "  [6] Fortalezas y riesgos      [12] Aviso",
    ]

    # ── [1] Veredicto global ────────────────────────────────────────────
    L += _title(1, "VEREDICTO GLOBAL")
    score = _num(g("composite_score"))
    L += [
        _kv("Puntuación compuesta", f"{score:.1f} / 100" if score is not None else "—"),
        _kv("Valoración del modelo", _rec_es(g("recommendation"))),
        _kv("Nivel de convicción", CONV_ES.get(str(g("conviction_level") or "").upper(),
                                               _s(g("conviction_level")))),
        _kv("Horizonte temporal", g("time_horizon")),
    ]
    lq = _num(g("long_term_quality_score"))
    if lq is not None:
        L.append(_kv("Calidad a largo plazo", f"{lq:.1f} / 100"))
    if g("quality_verdict"):
        L.append(_kv("Veredicto de calidad", g("quality_verdict")))
    if g("asymmetry_direction"):
        L.append(_kv("Asimetría del riesgo", f"{_s(g('asymmetry_direction'))} "
                                             f"({_s(g('asymmetry_strength'))})"))
    L.append(_kv("Máquina de componer", g("is_compound_machine", False)))
    vetos = g("vetos_applied") or []
    if vetos:
        L += _sub("Vetos aplicados (penalizaciones automáticas)") + _bullets(vetos)

    # ── [2] Niveles de operación ────────────────────────────────────────
    L += _title(2, "NIVELES DE OPERACIÓN")
    entry  = _num(g("entry_price"))
    stop   = _num(g("stop_loss")) or _num(rlevels.get("stop"))
    target = _num(g("target_price")) or _num(rlevels.get("target"))
    L += [
        _kv("Precio de entrada", _money(entry)),
        _kv("Stop loss", _money(stop)),
        _kv("Precio objetivo", _money(target)),
        _kv("Ratio riesgo/beneficio", g("risk_reward")),
        _kv("Tamaño de posición", g("position_size_pct")),
        _kv("Precio actual (en vivo)", _money(precio_vivo)),
    ]
    if precio_vivo and stop:
        L.append(_kv("Distancia al stop", _pct((stop - precio_vivo) / precio_vivo * 100)))
    if precio_vivo and target:
        L.append(_kv("Distancia al objetivo", _pct((target - precio_vivo) / precio_vivo * 100)))
    if rlevels:
        L += _sub("Niveles recalculados en vivo") + _dump_dict(rlevels)

    # ── [3] Datos de mercado en vivo ────────────────────────────────────
    if info:
        L += _title(3, "DATOS DE MERCADO EN VIVO (verificados al descargar)")
        L += [
            _kv("Precio actual", _money(info.get("current_price"))),
            _kv("Capitalización", _big(info.get("market_cap"))),
            _kv("Máximo 52 semanas", _money(info.get("52w_high"))),
            _kv("Mínimo 52 semanas", _money(info.get("52w_low"))),
            _kv("Volumen medio", _s(info.get("avg_volume"))),
            _kv("Beta", info.get("beta")),
            _kv("Industria", info.get("industry")),
            _kv("A qué se dedica", live.get("negocio") or _negocio(info)),
            _kv("País", info.get("country")),
            _kv("Empleados", info.get("employees")),
        ]
        L += _sub("Todos los datos de la ficha (crudo)")
        L += _dump_dict({k: v for k, v in info.items()
                         if k not in ("description",)})
        desc = str(info.get("description") or "").strip()
        if desc:
            L += _sub("Descripción del negocio") + _para(desc[:1500])

    # ── [4] Puntuaciones ────────────────────────────────────────────────
    L += _title(4, "PUNTUACIONES Y DESGLOSE")
    reports = g("reports") or {}
    L += _sub("Puntuación de cada bloque")
    for key, nombre in AGENT_ORDER:
        r = reports.get(key)
        if not r:
            continue
        sc = _num(getattr(r, "score", None))
        conv = CONV_ES.get(str(getattr(r, "conviction", "") or "").upper(),
                           _s(getattr(r, "conviction", None)))
        L.append(f"  {nombre.split(' — ')[0].ljust(16)}: "
                 f"{(f'{sc:.0f}' if sc is not None else '—').rjust(3)}/100   "
                 f"convicción {conv}")
    if g("score_breakdown"):
        L += _sub("Contribución al score compuesto") + _dump_dict(g("score_breakdown"))
    if g("snowflake"):
        L += _sub("Perfil de la acción (0-100 por dimensión)") + _dump_dict(g("snowflake"))

    # ── [5] Tesis ───────────────────────────────────────────────────────
    L += _title(5, "TESIS DE INVERSIÓN")
    L += _para(g("investment_thesis"))

    # ── [6] Fortalezas y riesgos ────────────────────────────────────────
    L += _title(6, "FORTALEZAS Y RIESGOS CLAVE")
    L += _sub("Fortalezas") + _bullets(g("key_strengths"))
    L += _sub("Riesgos") + _bullets(g("key_risks"))
    L += _sub("Estrategia de entrada") + _para(g("entry_strategy"))
    L += _sub("Estrategia de salida") + _para(g("exit_strategy"))

    # ── [7] Alpha ───────────────────────────────────────────────────────
    L += _title(7, "OPORTUNIDAD DETECTADA")
    L += _para(g("alpha_opportunity"))

    # ── [8] Indicadores técnicos en vivo ────────────────────────────────
    tech_rd = getattr(reports.get("technical"), "raw_data", {}) or {}
    ind_d = ind or (tech_rd.get("daily_indicators") or {})
    ind_w = live.get("indicators_weekly") or tech_rd.get("weekly_indicators") or {}
    rs    = live.get("rs") or tech_rd.get("rs") or {}
    klev  = live.get("key_levels") or tech_rd.get("key_levels") or {}
    # Lo que se vuelca aquí no se repite luego en el bloque técnico de [10].
    ya_volcado = set()
    if ind_d or ind_w or rs or klev:
        L += _title(8, "INDICADORES TÉCNICOS EN VIVO")
        if ind_d:
            L += _sub("Diario") + _dump_dict(ind_d)
            ya_volcado.add("daily_indicators")
        if ind_w:
            L += _sub("Semanal") + _dump_dict(ind_w)
            ya_volcado.add("weekly_indicators")
        if rs:
            L += _sub("Fuerza relativa frente al S&P 500") + _dump_dict(rs)
            ya_volcado.add("rs")
        if klev:
            L += _sub("Niveles clave") + _dump_dict(klev)
            ya_volcado.add("key_levels")

    # ── [9] Últimas sesiones ────────────────────────────────────────────
    ohlcv = live.get("ohlcv") or []
    if ohlcv:
        L += _title(9, "ÚLTIMAS SESIONES (precio de cierre y volumen)")
        L.append("  fecha        apertura    máximo     mínimo     cierre     volumen")
        for row in ohlcv:
            try:
                if _num(row.get("close")) is None:
                    continue
                L.append("  " + " ".join([
                    str(row.get("date", ""))[:10].ljust(12),
                    f"{_num(row.get('open')) or 0:>9,.2f}",
                    f"{_num(row.get('high')) or 0:>9,.2f}",
                    f"{_num(row.get('low')) or 0:>9,.2f}",
                    f"{_num(row.get('close')) or 0:>9,.2f}",
                    f"{_num(row.get('volume')) or 0:>14,.0f}",
                ]))
            except Exception:
                continue

    # ── [10] Análisis por bloque ────────────────────────────────────────
    L += _title(10, "ANÁLISIS DETALLADO POR BLOQUE (texto íntegro de cada análisis)")
    # AGENT_ORDER fija el orden de la app; cualquier bloque nuevo que apareciera
    # en el análisis se vuelca igualmente al final, para no perder nada.
    orden = AGENT_ORDER + [(k, k.upper()) for k in reports
                           if k not in {a for a, _ in AGENT_ORDER}]
    for key, nombre in orden:
        r = reports.get(key)
        if not r:
            continue
        sc = _num(getattr(r, "score", None))
        conv = CONV_ES.get(str(getattr(r, "conviction", "") or "").upper(),
                           _s(getattr(r, "conviction", None)))
        L += ["", SEP_L, f"{nombre}", SEP_L,
              _kv("Puntuación", f"{sc:.0f} / 100" if sc is not None else "—"),
              _kv("Convicción", conv)]
        err = getattr(r, "error", None)
        if err:
            L.append(_kv("Incidencia al generar", err))
        subs = getattr(r, "sub_scores", None) or {}
        if subs:
            L += _sub("Sub-puntuaciones") + _dump_dict(subs)
        km = getattr(r, "key_metrics", None) or {}
        if km:
            L += _sub("Métricas clave (nombre técnico: valor)") + _dump_dict(km)
        L += _sub("Señales positivas") + _bullets(getattr(r, "pros", None))
        L += _sub("Señales de riesgo") + _bullets(getattr(r, "cons", None))
        L += _sub("Análisis") + _para(getattr(r, "analysis", None))
        omitir = RAW_SKIP | (ya_volcado if key == "technical" else set())
        rd = {k: v for k, v in (getattr(r, "raw_data", None) or {}).items()
              if str(k).lower() not in omitir}
        if rd:
            L += _sub("Datos de respaldo del bloque") + _dump_dict(rd)

    # ── [11] Datos vivos complementarios ────────────────────────────────
    L += _title(11, "DATOS VIVOS COMPLEMENTARIOS")

    holders = live.get("holders") or {}
    if holders:
        insiders = holders.get("insider_transactions") or []
        L += _sub("Institucionales y directivos")
        L += _dump_dict({k: v for k, v in holders.items()
                         if k != "insider_transactions"})
        if insiders:
            L += _sub("Operaciones recientes de directivos")
            for t in insiders[:15]:
                if isinstance(t, dict):
                    L.append("  · " + "; ".join(f"{k}={_s(v)}" for k, v in t.items()
                                                if v not in (None, "", [], {})))

    earnings = live.get("earnings") or {}
    if earnings:
        L += _sub("Resultados trimestrales") + _dump_dict(earnings)

    events = live.get("events") or {}
    if events:
        upcoming = events.get("upcoming") or []
        if upcoming:
            L += _sub("Agenda de eventos corporativos")
            for e in upcoming[:15]:
                if isinstance(e, dict):
                    dias = e.get("days_from_today")
                    dias_txt = f" (en {dias} días)" if isinstance(dias, (int, float)) else ""
                    L.append(f"  · {_s(e.get('date'))}{dias_txt} — "
                             f"{_s(e.get('title') or e.get('type'))}")

    news = live.get("news") or []
    if news:
        L += _sub("Noticias recientes")
        for n in news[:10]:
            if isinstance(n, dict):
                edad = _num(n.get("age_hours"))
                edad_txt = f" [hace {edad:.0f} h]" if edad is not None else ""
                L.append(f"  · {_s(n.get('title'))}{edad_txt}")

    macro = live.get("macro") or {}
    if macro:
        L += _sub("Entorno de mercado") + _dump_dict(macro)

    # ── [12] Aviso ──────────────────────────────────────────────────────
    L += _title(12, "AVISO")
    L += [
        "  Informe educativo generado por DLP Market Analyzer. No es una",
        "  recomendación de inversión ni asesoramiento financiero personalizado.",
        "  Las puntuaciones y los textos de análisis proceden de modelos de IA",
        "  sobre datos de mercado; los precios y métricas marcados como «en",
        "  vivo» corresponden al momento de la descarga indicado en la cabecera.",
        "",
        f"  Generado: {ahora}  ·  {ticker}  ·  DLP Market Analyzer",
        SEP_H,
        "",
    ]

    return "\n".join(str(x) for x in L)
