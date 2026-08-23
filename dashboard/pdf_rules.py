"""
dashboard/pdf_rules.py — Reglas deterministas del Informe DLP.

Todo lo que aquí se "decide" sale de plantillas y umbrales sobre los datos que
ya trae el análisis: semáforo y frase de cada métrica fundamental, lectura de
cada píldora, veredicto de cada bloque, traducción de enums y limpieza de jerga.
Cero llamadas a Anthropic. Nunca lanza: cualquier dato raro acaba en SIN DATO.
"""
import re
from datetime import datetime

from dashboard.pdf_theme import (BIEN, REGULAR, MAL, SIN_DATO, INFO, Estado,
                                 _score_color)


# ═════════════════════════════════════════════════════════════════════════
# Utilidades numéricas y de texto
# ═════════════════════════════════════════════════════════════════════════
_AUSENTE = re.compile(r"^\s*(n/?a|n/?d|none|null|nan|sin datos?|no disponible|—|-)?\s*$", re.I)


def _to_float(val, default=None):
    """float o default. Con strings extrae el PRIMER número ('4.3% si…' → 4.3).
    'N/A', '—', NaN e infinitos → default."""
    if val is None or isinstance(val, bool):
        return default
    if isinstance(val, (int, float)):
        try:
            f = float(val)
            return f if (f == f and f not in (float("inf"), float("-inf"))) else default
        except Exception:
            return default
    s = str(val).strip()
    if _AUSENTE.match(s):
        return default
    m = re.search(r"-?\d+(?:[.,]\d+)?", s.replace(",", "."))
    if not m:
        return default
    try:
        return float(m.group(0))
    except Exception:
        return default


def _es_ausente(val) -> bool:
    return val is None or (isinstance(val, str) and bool(_AUSENTE.match(val)))


def _extract_ratio(s, default="—") -> str:
    """'1.16:1 a precio actual; 1.85:1 si…' → '1.16:1'."""
    if not s:
        return default
    m = re.search(r"\d+(?:[.,]\d+)?\s*[:\\/]\s*\d+(?:[.,]\d+)?", str(s))
    return m.group(0).replace(" ", "").replace(",", ".") if m else default


def _truncate_by_sentence(text: str, max_chars: int) -> str:
    """Corta por oración completa sin pasar de max_chars; «…» solo si corta."""
    if not text:
        return ""
    cleaned = re.sub(r"\s+", " ", str(text)).strip()
    if len(cleaned) <= max_chars:
        return cleaned
    sentences = [s.strip() for s in
                 re.split(r"(?<=[.!?])\s+(?=[A-ZÁÉÍÓÚÑ¿¡«\"0-9])", cleaned) if s.strip()]
    out = ""
    for s in sentences:
        cand = (out + " " + s).strip() if out else s
        if len(cand) > max_chars:
            break
        out = cand
    if not out:
        words, out = cleaned.split(), ""
        for w in words:
            cand = (out + " " + w).strip() if out else w
            if len(cand) + 1 > max_chars:
                break
            out = cand
        return out.rstrip(",;: ") + "…"
    return out if len(out) == len(cleaned) else out.rstrip(".!? ") + "…"


def _n(v, dec=1) -> str:
    """Número 'humano': entero si es grande, 1 decimal si es pequeño."""
    v = float(v)
    if abs(v) >= 100:
        return f"{v:,.0f}"
    if abs(v) >= 10 or dec == 0:
        return f"{v:.0f}" if abs(v - round(v)) < 0.05 else f"{v:.1f}"
    return f"{v:.{dec}f}"


def _money(v) -> str:
    f = _to_float(v)
    return f"${f:,.2f}" if f is not None else "—"


# ═════════════════════════════════════════════════════════════════════════
# Lenguaje: jerga → español llano (determinista)
# ═════════════════════════════════════════════════════════════════════════
# Glosario técnico → llano. Cada patrón lleva un lookahead negativo `(?!\s*\()`:
# si el término ya viene explicado entre paréntesis ("moat (ventaja competitiva…)")
# se deja tal cual para no producir "ventaja competitiva (ventaja competitiva…)".
_TECH_TO_PLAIN_RAW = [
    (r"\bmoat\b",                "ventaja competitiva"),
    (r"\bMoat\b",                "Ventaja competitiva"),
    (r"\bROIC\b",                "rentabilidad del capital"),
    (r"\bROE\b",                 "rentabilidad sobre el patrimonio"),
    (r"\bROA\b",                 "rentabilidad sobre los activos"),
    (r"\bEV/EBITDA\b",           "múltiplo de valoración"),
    (r"\bFCF yield\b",           "flujo de caja libre sobre el precio"),
    (r"\bdividend yield\b",      "rentabilidad por dividendo"),
    (r"\bFCF\b",                 "flujo de caja libre"),
    (r"\bEPS\b",                 "ganancias por acción"),
    (r"\bTAM\b",                 "mercado total"),
    (r"\bTTM\b",                 "de los últimos 12 meses"),
    (r"\bcapex\b",               "inversión en activos"),
    (r"\bCapex\b",               "Inversión en activos"),
    (r"\bbeta\b",                "sensibilidad al mercado"),
    (r"\bguidance\b",            "previsiones de la empresa"),
    (r"\bGuidance\b",            "Previsiones de la empresa"),
    (r"\bguiding\b",             "sus previsiones"),
    (r"\bconsensus\b",           "consenso de analistas"),
    (r"\bmega-cap\b",            "empresa de gran tamaño"),
    (r"\bmid-cap\b",             "empresa de tamaño medio"),
    (r"\bsmall-cap\b",           "empresa pequeña"),
    (r"\bbuybacks?\b",           "recompras de acciones"),
    (r"\bearnings beats?\b",     "trimestres superando expectativas"),
    (r"\bbeat rate\b",           "tasa de superaciones"),
    (r"\bupgrades?\b",           "mejoras de recomendación"),
    (r"\bdowngrades?\b",         "rebajas de recomendación"),
    (r"\bRSI\b",                 "indicador de fuerza (RSI)"),
    (r"\bMACD\b",                "indicador de impulso (MACD)"),
    (r"\bSMA\b",                 "media móvil"),
    (r"\bATR\b",                 "volatilidad típica"),
    (r"\bOBV\b",                 "volumen acumulado"),
    (r"\bStage 1\b",             "fase de base (lateral)"),
    (r"\bStage 2\b",             "fase de subida sostenida"),
    (r"\bStage 3\b",             "fase de techo"),
    (r"\bStage 4\b",             "fase de bajada sostenida"),
    (r"\bbreakout\b",            "ruptura al alza"),
    (r"\bbreakdown\b",           "pérdida de soporte"),
    (r"\bpullback\b",            "retroceso"),
    (r"\bpull-back\b",           "retroceso"),
    (r"\bbounce\b",              "rebote"),
    (r"\brebound\b",             "rebote"),
    (r"\bdip\b",                 "bajada puntual"),
    (r"\brunway\b",              "recorrido de crecimiento"),
    (r"\bflywheel\b",            "círculo virtuoso"),
    (r"\bde-?rating\b",          "caída del múltiplo"),
    (r"\bre-?rating\b",          "revalorización del múltiplo"),
    (r"\boverhang\b",            "presión vendedora latente"),
    (r"\bchurn\b",               "pérdida de clientes"),
    (r"\bbacklog\b",             "pedidos pendientes"),
    (r"\bbookings\b",            "contratos firmados"),
    (r"\bramp-?up\b",            "aceleración"),
    (r"\bcash burn\b",           "quema de caja"),
    (r"\bburn rate\b",           "ritmo de quema de caja"),
    (r"\bcompounding\b",         "crecimiento compuesto"),
    (r"\bcompounders\b",         "empresas que multiplican su valor año tras año"),
    (r"\bcompounder\b",          "empresa que multiplica su valor año tras año"),
    (r"\bswing low\b",           "mínimo reciente"),
    (r"\bswing high\b",          "máximo reciente"),
    (r"\bstop[- ]loss\b",        "nivel de protección"),
    (r"\bstop\b",                "nivel de protección"),
    (r"\bcash flow\b",           "flujo de caja"),
    (r"\bshares\b",              "acciones"),
    (r"\bshock\b",               "golpe"),
    (r"\btrend\b",               "tendencia"),
    (r"\bSPY\b",                 "el S&P 500"),
    (r"\bRS\b",                  "fuerza relativa"),
    (r"\b52W\b",                 "52 semanas"),
    (r"\bQ([1-4])\b",            r"\1T"),
    (r"\bConsumer Discretionary\b", "consumo cíclico"),
    (r"\bConsumer Staples\b",    "consumo básico"),
    (r"\bHealthcare\b",          "salud"),
    (r"\bFinancials\b",          "sector financiero"),
    (r"\bIndustrials\b",         "sector industrial"),
    (r"\bUtilities\b",           "servicios públicos"),
    (r"\bReal Estate\b",         "sector inmobiliario"),
    (r"\bTechnology\b",          "tecnología"),
    (r"\bcatalysts?\b",          "catalizadores"),
    (r"\bspread\b",              "diferencial"),
    (r"\bdeleveraging\b",        "reducción de deuda"),
    (r"\bsetup\b",               "condiciones"),
    (r"\binsiders?\b",           "directivos"),
    (r"\bshort interest\b",      "apuestas a la baja"),
    (r"\bshorts?\b",             "apuestas a la baja"),
    (r"\bhyperscalers?\b",       "grandes empresas de nube"),
    (r"\bcrowded\b",             "masificado"),
    (r"\byields? a 10 años\b",   "tasas a 10 años"),
    (r"\byields?\b",             "rendimiento"),
    (r"\brisk-on\b",             "apetito por el riesgo"),
    (r"\brisk-off\b",            "aversión al riesgo"),
    (r"\bbear market\b",         "mercado bajista"),
    (r"\bbull market\b",         "mercado alcista"),
    (r"\bsell-?off\b",           "ola de ventas"),
    (r"\brally\b",               "subida fuerte"),
    (r"\bmomentum\b",            "impulso"),
    (r"\bupside\b",              "potencial de subida"),
    (r"\bdownside\b",            "riesgo de caída"),
    (r"\bstance\b",              "postura"),
    (r"\bfalse breaks?\b",       "rupturas falsas"),
    (r"\bP/E forward\b",         "múltiplo P/E estimado"),
    (r"\bforward P/E\b",         "múltiplo P/E estimado"),
    (r"\btrailing P/E\b",        "múltiplo P/E histórico"),
    (r"\bP/E trailing\b",        "múltiplo P/E histórico"),
    (r"\bforward\b",             "estimado"),
    (r"\btrailing\b",            "histórico"),
    (r"\bYoY\b",                 "interanual"),
    (r"\bQoQ\b",                 "trimestre a trimestre"),
    (r"\bearnings\b",            "resultados"),
    (r"\bquarters?\b",           "trimestres"),
    (r"\bstock\b",               "acción"),
    (r"\btarget\b",              "precio objetivo"),
    (r"\bmanagement\b",          "la dirección"),
    (r"\bvaluation\b",           "valoración"),
    (r"\bvaluación\b",           "valoración"),
    (r"\bpreciosando\b",         "descontando"),
]
# El lookahead salta el término solo si le sigue un paréntesis SIN dígitos
# (una explicación: "moat (ventaja competitiva…)"); "earnings (83 días)" sí se traduce.
_TECH_TO_PLAIN = [(re.compile(p + r"(?!\s*\([^)0-9]*\))"), r) for p, r in _TECH_TO_PLAIN_RAW]


def _simplify_lang(text: str) -> str:
    if not text:
        return ""
    out = str(text)
    for rx, rep in _TECH_TO_PLAIN:
        out = rx.sub(rep, out)
    out = re.sub(r"\(\s*\)", "", out)
    return re.sub(r"[ \t]+", " ", out).strip()


def _limpiar(text) -> str:
    """Texto de la IA listo para imprimir: jerga de `agents.base._traducir_texto`
    (la misma tabla de la app, regex determinista) + glosario del PDF."""
    if not text:
        return ""
    s = str(text)
    try:
        from agents.base import _traducir_texto
        s = _traducir_texto(s)
    except Exception:
        pass
    s = _simplify_lang(s)
    return re.sub(r"\s*\n\s*", "\n", s).strip()


# ── Enums de key_metrics → español ───────────────────────────────────────
_ENUM_ES = {
    "wide": "Amplia", "narrow": "Estrecha", "none": "Sin ventaja", "moderate": "Moderada",
    "low": "Bajo", "medium": "Medio", "high": "Alto", "critical": "Crítico",
    "very low": "Muy bajo", "very high": "Muy alto",
    "excellent": "Excelente", "good": "Buena", "average": "Media", "poor": "Pobre",
    "platform": "Plataforma", "saas": "Suscripción", "marketplace": "Mercado digital",
    "traditional": "Tradicional", "commodity": "Materia prima", "other": "Otro",
    "expanding rapidly": "Crece rápido", "expanding": "En expansión",
    "stable": "Estable", "contracting": "Encogiéndose", "flat": "Plana",
    "risk-on": "Apetito por el riesgo", "risk-off": "Aversión al riesgo",
    "neutral": "Neutral", "normal": "Normal", "inverted": "Invertida",
    "high negative": "Alta, en contra", "high positive": "Alta, a favor",
    "low negative": "Baja, en contra", "low positive": "Baja, a favor",
    "strong": "Fuerte", "weak": "Débil",
    "low <20": "Bajo", "elevated 20-30": "Elevado", "high >30": "Alto",
    "favorable": "Favorable", "unfavorable": "Desfavorable",
    "very bullish": "Muy alcista", "bullish": "Alcista",
    "very bearish": "Muy bajista", "bearish": "Bajista",
    "improving": "Mejorando", "deteriorating": "Empeorando",
    "accumulating": "Acumulando", "distributing": "Vendiendo",
    "buying": "Comprando", "selling": "Vendiendo", "strong buying": "Comprando con fuerza",
    "buy the fear": "El miedo crea oportunidad", "sell the hype": "La euforia avisa",
    "sell the greed": "La euforia avisa", "no signal": "Sin señal",
    "turnaround": "Recuperación", "defensive": "Defensivo", "defensivo": "Defensivo",
    "growth": "Crecimiento", "value": "Valor", "momentum": "Impulso",
    "disruption": "Disrupción", "disrupción": "Disrupción",
}
_ENUM_WORDS = [
    (re.compile(r"\bStage\b"), "Fase"), (re.compile(r"\bstage\b"), "fase"),
    (re.compile(r"\bdel float\b"), "del total"), (re.compile(r"\bfloat\b"), "en circulación"),
    (re.compile(r"\bYoY\b"), "interanual"), (re.compile(r"\bforward\b"), "estimado"),
    (re.compile(r"\btrailing\b"), "histórico"), (re.compile(r"\bbeats?\b"), "aciertos"),
    (re.compile(r"\bbullish\b"), "alcista"), (re.compile(r"\bbearish\b"), "bajista"),
    (re.compile(r"\bcontracting\b"), "en descenso"), (re.compile(r"\bexpanding\b"), "en aumento"),
    (re.compile(r"\bneutral\b"), "neutral"), (re.compile(r"\bimproving\b"), "mejorando"),
    (re.compile(r"\bdeteriorating\b"), "empeorando"), (re.compile(r"\bstrong\b"), "fuerte"),
    (re.compile(r"\bweak\b"), "débil"), (re.compile(r"\bwide\b"), "amplia"),
    (re.compile(r"\bnarrow\b"), "estrecha"), (re.compile(r"\bhigh\b"), "alto"),
    (re.compile(r"\bmedium\b"), "medio"), (re.compile(r"\blow\b"), "bajo"),
]


def _enum_es(v, default="—") -> str:
    """Valor categórico en español. Tolerante a None/strings largos."""
    if _es_ausente(v):
        return default
    s = str(v).strip()
    low = s.lower().strip(" .")
    if low in _ENUM_ES:
        return _ENUM_ES[low]
    base = re.split(r"\s*[\(—–-]\s*", low, maxsplit=1)[0].strip()
    if base in _ENUM_ES:
        return _ENUM_ES[base]
    out = s
    for rx, rep in _ENUM_WORDS:
        out = rx.sub(rep, out)
    return out[:1].upper() + out[1:]


def _es_sector(s) -> str:
    try:
        from data.industry_labels import sector_es
        t = sector_es(s)
        if t:
            return t
    except Exception:
        pass
    return str(s) if s else ""


def _negocio(sector, industry=None) -> str:
    try:
        from data.industry_labels import describe_business
        return describe_business(industry, sector) or ""
    except Exception:
        return ""


# ═════════════════════════════════════════════════════════════════════════
# Secciones del informe
# ═════════════════════════════════════════════════════════════════════════
SECCIONES = [
    dict(n=1, key="veredicto",     code="",   nav="VEREDICTO",
         titulo="VEREDICTO", subtitulo="La foto completa de la acción en una página"),
    dict(n=2, key="fundamentals",  code="FN", nav="FUNDAMENTALES",
         titulo="FUNDAMENTALES", subtitulo="Qué tan estable y rentable es la empresa",
         teoria="Los fundamentales miden la salud del negocio: cuánto crece, cuánto gana "
                "de verdad y cuánto debe. Es la base de todo."),
    dict(n=3, key="technical",     code="TC", nav="TÉCNICO",
         titulo="TÉCNICO", subtitulo="Hacia dónde va el precio y con cuánta fuerza",
         teoria="El análisis técnico lee el precio: su tendencia, su impulso y los niveles "
                "que importan. No dice si la empresa es buena; dice si es buen momento."),
    dict(n=4, key="future",        code="FU", nav="FUTURO Y SMART MONEY",
         titulo="FUTURO Y SMART MONEY",
         subtitulo="La ventaja competitiva que la protege y qué hace el dinero grande"),
    dict(n=5, key="context",       code="CT", nav="CONTEXTO",
         titulo="CONTEXTO DEL MERCADO",
         subtitulo="Los eventos que vienen, el entorno económico y el ánimo del mercado"),
    dict(n=6, key="risk",          code="RS", nav="RIESGO",
         titulo="RIESGO Y RECORRIDO DEL PRECIO",
         subtitulo="Cuánto puedes perder, cuánto puedes ganar y cuánto invertir",
         teoria="Invertir bien no es acertar siempre: es que, cuando aciertas, ganes más de "
                "lo que pierdes cuando fallas. Aquí medimos esa relación."),
    dict(n=7, key="conclusion",    code="",   nav="CONCLUSIÓN",
         titulo="CONCLUSIÓN", subtitulo="Lo que pesa a favor, lo que pesa en contra y el plan"),
]

# Orden y nombres OFICIALES de los 8 bloques (los mismos de la app)
BLOQUES = [
    ("fundamentals",  "FN", "Fundamentales"),
    ("technical",     "TC", "Técnico"),
    ("future",        "FU", "Futuro"),
    ("institutional", "SM", "Smart Money"),
    ("catalysts",     "CT", "Catalizadores"),
    ("macro",         "MC", "Macro"),
    ("sentiment",     "SN", "Sentimiento"),
    ("risk",          "RS", "Riesgo"),
]

# Rangos de las sub-notas tal como los pide el prompt de cada agente
_SUB_RANGOS = {
    "fundamentals":  [("quality", "Calidad", 25), ("growth", "Crecimiento", 25),
                      ("valuation", "Valoración", 25), ("financial_health", "Solidez financiera", 25)],
    "technical":     [("trend_quality", "Calidad de la tendencia", 33), ("momentum", "Impulso", 33),
                      ("setup_quality", "Momento de entrada", 34)],
    "future":        [("moat_quality", "Ventaja competitiva", 25), ("growth_runway", "Recorrido de crecimiento", 25),
                      ("disruption_resilience", "Resistencia a la disrupción", 25),
                      ("management_capital_allocation", "Uso del capital", 25)],
    "institutional": [("insider_signal", "Señal de los directivos", 33),
                      ("institutional_quality", "Calidad institucional", 33),
                      ("short_interest_dynamic", "Presión de cortos", 34)],
    "catalysts":     [("earnings_momentum", "Impulso de resultados", 34), ("catalyst_quality", "Calidad de catalizadores", 33),
                      ("analyst_revision_trend", "Revisiones de analistas", 33)],
    "macro":         [("macro_environment", "Entorno macro", 34), ("sector_rotation", "Rotación sectorial", 33),
                      ("liquidity_conditions", "Liquidez", 33)],
    "sentiment":     [("news_sentiment", "Noticias", 34), ("narrative_momentum", "Narrativa", 33),
                      ("contrarian_value", "Valor contrario", 33)],
    "risk":          [("risk_reward_quality", "Relación riesgo/beneficio", 40),
                      ("volatility_manageability", "Volatilidad manejable", 30),
                      ("downside_protection", "Protección a la baja", 30)],
}


# ═════════════════════════════════════════════════════════════════════════
# Acceso blindado al análisis
# ═════════════════════════════════════════════════════════════════════════
def _rep(a, key):
    return (getattr(a, "reports", None) or {}).get(key)


def _rep_ok(r) -> bool:
    return r is not None and not getattr(r, "error", None)


def _km(r) -> dict:
    return (getattr(r, "key_metrics", None) or {}) if r else {}


def _rd(r) -> dict:
    return (getattr(r, "raw_data", None) or {}) if r else {}


def _score(r):
    return _to_float(getattr(r, "score", None)) if _rep_ok(r) else None


def _pros(r, n=2) -> list:
    return [_limpiar(p) for p in (getattr(r, "pros", None) or []) if p][:n]


def _cons(r, n=2) -> list:
    return [_limpiar(p) for p in (getattr(r, "cons", None) or []) if p][:n]


def _score_rows(a) -> list:
    """Filas del desglose: (code, nombre, score|None, color). Nunca inventa un 50."""
    sb = getattr(a, "score_breakdown", None) or {}
    rows = []
    for key, code, nombre in BLOQUES:
        r = _rep(a, key)
        s = _score(r)
        if s is None and r is None:
            s = _to_float(sb.get(key))
        rows.append((code, nombre, s, _score_color(s) if s is not None else None))
    return rows


def _pilares(a, agent_key) -> list:
    """Sub-notas de un bloque escaladas a 0-100, para _native_bars."""
    r = _rep(a, agent_key)
    subs = (getattr(r, "sub_scores", None) or {}) if r else {}
    rows = []
    for key, nombre, tope in _SUB_RANGOS.get(agent_key, []):
        v = _to_float(subs.get(key))
        s = max(0.0, min(100.0, v / tope * 100.0)) if (v is not None and tope) else None
        rows.append((None, nombre, s, _score_color(s) if s is not None else None))
    return rows


# ═════════════════════════════════════════════════════════════════════════
# Veredictos por bloque
# ═════════════════════════════════════════════════════════════════════════
def _tier(score) -> str:
    s = _to_float(score, default=50.0)
    return "alto" if s >= 62 else "medio" if s >= 45 else "bajo"


_TIER_ESTADO = {"alto": BIEN, "medio": REGULAR, "bajo": MAL}

_VEREDICTO = {
    "future":        {"alto": "Ventaja duradera y recorrido por delante",
                      "medio": "Negocio viable, ventaja por confirmar",
                      "bajo": "Futuro con dudas reales"},
    "institutional": {"alto": "Los grandes fondos la respaldan",
                      "medio": "Sin movimiento claro del dinero grande",
                      "bajo": "Poco respaldo de los grandes fondos"},
    "catalysts":     {"alto": "Eventos cercanos que pueden impulsar",
                      "medio": "Sin un impulso claro inmediato",
                      "bajo": "Pocos catalizadores a la vista"},
    "macro":         {"alto": "El entorno juega a favor",
                      "medio": "Entorno neutro",
                      "bajo": "El entorno juega en contra"},
    "sentiment":     {"alto": "Ánimo positivo hacia la empresa",
                      "medio": "Ánimo neutral",
                      "bajo": "Ánimo negativo hacia la empresa"},
}

_CONCLUSIONS = {
    "fundamentals": {"alto": "La empresa gana dinero de forma sólida y constante. Sus finanzas son sanas.",
                     "medio": "La empresa es rentable, pero tiene algún punto financiero por mejorar.",
                     "bajo": "Sus finanzas muestran debilidades: la rentabilidad o la deuda preocupan."},
    "technical":    {"alto": "El precio viene subiendo de forma sostenida. La tendencia acompaña.",
                     "medio": "El precio se mueve de lado, sin una dirección clara por ahora.",
                     "bajo": "El precio viene débil o de bajada."},
    "future":       {"alto": "Tiene una ventaja difícil de copiar y espacio para crecer por años.",
                     "medio": "Es un negocio viable, pero su ventaja a largo plazo no es del todo clara.",
                     "bajo": "Hay dudas reales sobre qué tan fuerte será este negocio en el futuro."},
    "institutional": {"alto": "Los grandes inversores están comprando y respaldan la acción.",
                      "medio": "Los grandes inversores están a la expectativa, sin un movimiento claro.",
                      "bajo": "Por ahora hay poco respaldo de los grandes inversores."},
    "catalysts":    {"alto": "Tiene eventos cercanos (como resultados) que pueden impulsar el precio.",
                     "medio": "Tiene algunos eventos por delante, pero sin un impulso claro inmediato.",
                     "bajo": "No se ven eventos importantes que muevan el precio en el corto plazo."},
    "macro":        {"alto": "El entorno general del mercado juega a su favor.",
                     "medio": "El entorno general del mercado está neutro para la empresa.",
                     "bajo": "El entorno general del mercado juega en su contra ahora mismo."},
    "sentiment":    {"alto": "El ánimo y las noticias sobre la empresa son positivos.",
                     "medio": "El ánimo del mercado sobre la empresa es neutral.",
                     "bajo": "El ánimo y las noticias sobre la empresa son negativos."},
    "risk":         {"alto": "Lo que puede ganar supera con claridad a lo que puede perder.",
                     "medio": "El posible premio y el posible riesgo están bastante parejos.",
                     "bajo": "Hoy se arriesga más de lo que se puede ganar."},
}


def _conclusion(rkey, score) -> str:
    table = _CONCLUSIONS.get(rkey)
    return table[_tier(score)] if table else ""


def _verdict_generic(rkey, score):
    t = _tier(score)
    texto = _VEREDICTO.get(rkey, {}).get(t, "")
    return texto, _TIER_ESTADO[t]()


def _verdict_stability(score):
    s = _to_float(score, default=50.0)
    if s >= 80: return "Empresa muy estable y rentable", BIEN()
    if s >= 65: return "Empresa estable con buenas finanzas", BIEN()
    if s >= 50: return "Bases sólidas, con puntos por mejorar", REGULAR()
    if s >= 35: return "Empresa con fragilidades visibles", REGULAR()
    return "Empresa con fragilidades importantes", MAL()


def _verdict_trend(score, stage_value):
    s = _to_float(score, default=50.0)
    st = _to_float(stage_value)
    if st == 2 or s >= 70: return "Tendencia alcista clara", BIEN()
    if st == 3: return "Techo: el impulso se agota", REGULAR()
    if st == 4 or s < 35: return "Tendencia bajista en curso", MAL()
    if s >= 55: return "Tendencia alcista moderada", BIEN()
    if s >= 45: return "Sin dirección clara", REGULAR()
    return "Tendencia débil", MAL()


def _verdict_asymmetry(direction, strength):
    d = str(direction or "").lower()
    f = str(strength or "").lower()
    if "up" in d:
        return ("Asimetría a favor" + (" y fuerte" if "strong" in f else ""), BIEN())
    if "down" in d:
        return ("Asimetría en contra" + (" y fuerte" if "strong" in f else ""), MAL())
    if "bal" in d:
        return "Riesgo equilibrado", REGULAR()
    return "Asimetría sin medir", SIN_DATO()


# ═════════════════════════════════════════════════════════════════════════
# Fundamentales: las 6 métricas con semáforo + frase
# ═════════════════════════════════════════════════════════════════════════
def _meter_pct(value, lo, hi, invert=False):
    try:
        pct = (float(value) - lo) / (hi - lo) * 100.0
    except Exception:
        return None
    pct = max(2.0, min(98.0, pct))
    return 100.0 - pct if invert else pct


def _from_km(km: dict, keys, *, pct_if_over=None):
    """Primer valor numérico de key_metrics; detecta 'N/A' y 'negativ…'."""
    for k in keys:
        raw = km.get(k)
        if _es_ausente(raw):
            continue
        s = str(raw)
        if re.search(r"\bN/?A\b", s, re.I) and not re.search(r"-?\d", s):
            return None, s
        v = _to_float(s)
        if v is None:
            return None, s
        if pct_if_over is not None and v > pct_if_over:
            v = v / 100.0
        return v, s
    return None, None


_SIN_DATO_FRASE = "No pudimos medir este dato esta vez; no afecta la calificación."


def _fundamentales_specs(a) -> list:
    r = _rep(a, "fundamentals")
    rd, km = _rd(r), _km(r)
    ratios = rd.get("ratios") if isinstance(rd.get("ratios"), dict) else {}
    info = rd.get("info_snippet") if isinstance(rd.get("info_snippet"), dict) else {}

    def val(rkey, kmkeys, pct_if_over=None):
        v = _to_float(ratios.get(rkey))
        if v is not None:
            return v, None
        return _from_km(km, kmkeys, pct_if_over=pct_if_over)

    growth, _ = val("revenue_growth_yoy", ("revenue_growth", "revenue_growth_yoy"))
    roic, _ = val("roic", ("roic", "roe"))
    margin, _ = val("operating_margin", ("operating_margin",))
    fcf, _ = val("fcf_yield", ("fcf_yield",))
    de, _ = val("debt_to_equity", ("debt_equity", "debt_to_equity"), pct_if_over=30)
    pe = _to_float(info.get("pe"))
    pe_raw = None
    if pe is None:
        pe, pe_raw = _from_km(km, ("pe_ratio", "forward_pe"))
    pe_sin_ganancias = (pe is not None and pe <= 0) or \
        (pe is None and pe_raw is not None and re.search(r"negativ|pérdid|loss", pe_raw, re.I))

    return [
        _evaluar_metrica("growth", growth),
        _evaluar_metrica("roic", roic),
        _evaluar_metrica("margin", margin),
        _evaluar_metrica("fcf", fcf),
        _evaluar_metrica("de", de),
        _evaluar_metrica("pe", pe, sin_ganancias=pe_sin_ganancias),
    ]


_QUE_MIDE = {
    "growth": "Cuánto cambiaron las ventas frente al mismo periodo del año anterior.",
    "roic":   "Cuánta ganancia produce el dinero invertido en el negocio (ROIC).",
    "margin": "Qué parte de cada venta queda después de los costes de operar.",
    "fcf":    "El efectivo que sobra tras invertir en el negocio, frente a lo que vale en bolsa.",
    "de":     "Cuánto debe la empresa comparado con lo que es suyo de verdad.",
    "pe":     "Cuántos años de ganancias actuales estás pagando con el precio de hoy.",
}
_LABEL = {
    "growth": "CRECIMIENTO DE INGRESOS", "roic": "RENTABILIDAD DEL CAPITAL",
    "margin": "MARGEN OPERATIVO", "fcf": "FLUJO DE CAJA LIBRE",
    "de": "DEUDA / PATRIMONIO", "pe": "PRECIO / GANANCIAS (P/E)",
}


def _evaluar_metrica(clave, v, *, sin_ganancias=False) -> dict:
    spec = dict(label=_LABEL[clave], que_mide=_QUE_MIDE[clave], unidad=None)
    if clave == "pe" and sin_ganancias:
        spec.update(valor_fmt="—", estado=MAL("SIN GANANCIAS"), pct_meter=None,
                    frase="No tiene ganancias en el último año, así que este múltiplo no se "
                          "puede calcular: hoy se paga por expectativas.")
        return spec
    if v is None:
        spec.update(valor_fmt="—", estado=SIN_DATO(), pct_meter=None, frase=_SIN_DATO_FRASE)
        return spec
    v = float(v)

    if clave == "growth":
        spec["valor_fmt"] = f"{v:+.1f}%"
        spec["pct_meter"] = _meter_pct(v, -10, 30)
        if v >= 10:
            spec["estado"], spec["frase"] = BIEN(), (
                f"Vende un {_n(v)}% más que hace un año: crece a buen ritmo, por encima de lo habitual.")
        elif v >= 0:
            spec["estado"], spec["frase"] = REGULAR(), (
                f"Vende un {_n(v)}% más que hace un año: crece, pero despacio; conviene vigilar que no se estanque.")
        else:
            spec["estado"], spec["frase"] = MAL(), (
                f"Vende un {_n(abs(v))}% menos que hace un año: el negocio se está encogiendo en vez de crecer.")

    elif clave == "roic":
        spec["valor_fmt"] = f"{v:.1f}%"
        spec["pct_meter"] = _meter_pct(v, 0, 25)
        if v > 15:
            spec["estado"], spec["frase"] = BIEN(), (
                f"Por cada $100 que invierte en el negocio genera ${_n(v)}: crea valor con claridad.")
        elif v >= 8:
            spec["estado"], spec["frase"] = REGULAR(), (
                f"Por cada $100 que invierte en el negocio genera ${_n(v)}: rentabilidad aceptable, sin ser destacada.")
        elif v >= 0:
            spec["estado"], spec["frase"] = MAL(), (
                f"Por cada $100 que invierte en el negocio genera solo ${_n(v)}: el capital rinde poco.")
        else:
            spec["estado"], spec["frase"] = MAL(), (
                f"Por cada $100 invertidos pierde ${_n(abs(v))}: hoy el capital destruye valor en vez de crearlo.")

    elif clave == "margin":
        spec["valor_fmt"] = f"{v:.1f}%"
        spec["pct_meter"] = _meter_pct(v, 0, 32)
        if v > 20:
            spec["estado"], spec["frase"] = BIEN(), (
                f"De cada $100 que vende le quedan ${_n(v)} tras pagar el funcionamiento: negocio eficiente.")
        elif v >= 10:
            spec["estado"], spec["frase"] = REGULAR(), (
                f"De cada $100 que vende le quedan ${_n(v)}: margen razonable, con poco colchón.")
        elif v >= 0:
            spec["estado"], spec["frase"] = MAL(), (
                f"De cada $100 que vende apenas le quedan ${_n(v)}: cualquier tropiezo se come la ganancia.")
        else:
            spec["estado"], spec["frase"] = MAL(), (
                f"Pierde ${_n(abs(v))} por cada $100 que vende: el negocio aún no se paga a sí mismo.")

    elif clave == "fcf":
        spec["valor_fmt"] = f"{v:.1f}%"
        spec["pct_meter"] = _meter_pct(v, 0, 8)
        if v > 5:
            spec["estado"], spec["frase"] = BIEN(), (
                f"Genera ${_n(v)} de caja libre por cada $100 de valor en bolsa: efectivo real y abundante.")
        elif v >= 2:
            spec["estado"], spec["frase"] = REGULAR(), (
                f"Genera ${_n(v)} de caja libre por cada $100 en bolsa: el efectivo que produce es moderado para lo que vale.")
        elif v >= 0:
            spec["estado"], spec["frase"] = MAL(), (
                f"Genera solo ${_n(v)} de caja libre por cada $100 en bolsa: poco efectivo para lo que cuesta.")
        else:
            spec["estado"], spec["frase"] = MAL(), (
                f"Quema caja: gasta más efectivo del que genera ({_n(abs(v))}% de su valor en bolsa al año).")

    elif clave == "de":
        spec["valor_fmt"] = f"{v:.2f}x"
        spec["pct_meter"] = _meter_pct(v, 0, 2.5, invert=True)
        if v < 0:
            spec["estado"], spec["frase"] = MAL(), (
                "Debe más de lo que tiene: el patrimonio es negativo y el balance está bajo presión.")
            spec["pct_meter"] = 2.0
        elif v < 0.5:
            spec["estado"], spec["frase"] = BIEN(), (
                f"Por cada $1 de patrimonio debe ${v:.2f}: deuda baja, balance cómodo.")
        elif v <= 1.5:
            spec["estado"], spec["frase"] = REGULAR(), (
                f"Por cada $1 de patrimonio debe ${v:.2f}: deuda manejable, pero ya pesa.")
        else:
            spec["estado"], spec["frase"] = MAL(), (
                f"Por cada $1 de patrimonio debe ${v:.2f}: deuda muy alta; depende de que el negocio no falle.")

    elif clave == "pe":
        spec["valor_fmt"] = f"{v:.1f}x"
        spec["pct_meter"] = _meter_pct(v, 8, 45, invert=True)
        if 5 <= v <= 18:
            spec["estado"], spec["frase"] = BIEN("BARATO"), (
                f"Pagas ${_n(v)} por cada $1 de ganancia anual: barato frente al mercado (~20), a veces por buenas razones.")
        elif v <= 30:
            spec["estado"], spec["frase"] = REGULAR("NORMAL"), (
                f"Pagas ${_n(v)} por cada $1 de ganancia anual: en línea con lo habitual del mercado (~20).")
        elif v < 5:
            spec["estado"], spec["frase"] = REGULAR("MUY BAJO"), (
                f"Pagas ${_n(v)} por cada $1 de ganancia anual: tan bajo que el mercado desconfía de que esas ganancias duren.")
        else:
            spec["estado"], spec["frase"] = MAL("CARO"), (
                f"Pagas ${_n(v)} por cada $1 de ganancia anual: caro; el precio ya descuenta mucho crecimiento futuro.")
    return spec


# ═════════════════════════════════════════════════════════════════════════
# Píldoras por bloque
# ═════════════════════════════════════════════════════════════════════════
def _pill_spec(label, value, estado, reading=None):
    return dict(label=label, value=value, estado=estado, reading=reading)


def _pills_technical(a) -> list:
    r = _rep(a, "technical")
    di = _rd(r).get("daily_indicators") or {}
    km = _km(r)
    out = []
    # Etapa
    st = _to_float(di.get("stage"))
    if st is None:
        st = _to_float(km.get("stage"))
    if st == 1:   out.append(_pill_spec("ETAPA DEL PRECIO", "Fase 1", REGULAR(), "Base: el precio se está formando"))
    elif st == 2: out.append(_pill_spec("ETAPA DEL PRECIO", "Fase 2", BIEN(), "Subida sostenida: la tendencia acompaña"))
    elif st == 3: out.append(_pill_spec("ETAPA DEL PRECIO", "Fase 3", REGULAR(), "Techo: el impulso se agota"))
    elif st == 4: out.append(_pill_spec("ETAPA DEL PRECIO", "Fase 4", MAL(), "Bajada sostenida: la tendencia en contra"))
    else:         out.append(_pill_spec("ETAPA DEL PRECIO", "—", SIN_DATO(), "No se pudo determinar la fase"))
    # RSI
    rsi = _to_float(di.get("rsi_14"))
    if rsi is None:
        rsi = _to_float(km.get("rsi_14"))
    if rsi is None:       out.append(_pill_spec("FUERZA (RSI 14)", "—", SIN_DATO(), "Sin dato esta vez"))
    elif rsi < 30:        out.append(_pill_spec("FUERZA (RSI 14)", f"{rsi:.0f}", REGULAR(), "Sobreventa: cayó mucho y rápido"))
    elif rsi < 40:        out.append(_pill_spec("FUERZA (RSI 14)", f"{rsi:.0f}", REGULAR(), "Débil, aunque sin sobreventa"))
    elif rsi <= 65:       out.append(_pill_spec("FUERZA (RSI 14)", f"{rsi:.0f}", BIEN(), "Zona sana, sin excesos"))
    elif rsi <= 70:       out.append(_pill_spec("FUERZA (RSI 14)", f"{rsi:.0f}", REGULAR(), "Algo caliente: subió rápido"))
    else:                 out.append(_pill_spec("FUERZA (RSI 14)", f"{rsi:.0f}", REGULAR(), "Sobrecompra: subió mucho y rápido"))
    # MACD
    h = _to_float(di.get("macd_hist"))
    if h is None:
        sig = str(km.get("macd_signal") or "").lower()
        h = 1 if "bull" in sig else -1 if "bear" in sig else None
        val = _enum_es(km.get("macd_signal"))
    else:
        val = f"{h:+.2f}"
    if h is None:   out.append(_pill_spec("IMPULSO (MACD)", "—", SIN_DATO(), "Sin dato esta vez"))
    elif h > 0:     out.append(_pill_spec("IMPULSO (MACD)", val, BIEN(), "Impulso a favor del precio"))
    elif h < 0:     out.append(_pill_spec("IMPULSO (MACD)", val, MAL(), "Impulso en contra del precio"))
    else:           out.append(_pill_spec("IMPULSO (MACD)", val, REGULAR(), "Impulso neutro"))
    # Distancia al máximo 52 s
    d52 = _to_float(di.get("pct_from_52w_high"))
    if d52 is None:
        d52 = _to_float(km.get("pct_from_52w_high"))
    if d52 is None:  out.append(_pill_spec("MÁXIMO DEL AÑO", "—", SIN_DATO(), "Sin dato esta vez"))
    elif d52 > -5:   out.append(_pill_spec("MÁXIMO DEL AÑO", f"{d52:+.1f}%", BIEN(), "Cerca de su máximo de 52 semanas"))
    elif d52 >= -20: out.append(_pill_spec("MÁXIMO DEL AÑO", f"{d52:+.1f}%", REGULAR(), "A medio camino de su máximo del año"))
    else:            out.append(_pill_spec("MÁXIMO DEL AÑO", f"{d52:+.1f}%", MAL(), "Lejos de su máximo de 52 semanas"))
    return out


def _vs_mercado_rows(a) -> list:
    r = _rep(a, "technical")
    di = _rd(r).get("daily_indicators") or {}
    rs = _rd(r).get("rs") or {}
    return [
        ("vs media de 50 días",  _to_float(di.get("price_vs_sma50_pct")),  "{:+.1f}%"),
        ("vs media de 200 días", _to_float(di.get("price_vs_sma200_pct")), "{:+.1f}%"),
        ("vs S&P 500 · 1 mes",   _to_float(rs.get("rs_1m")), "{:+.1f}%"),
        ("vs S&P 500 · 3 meses", _to_float(rs.get("rs_3m")), "{:+.1f}%"),
        ("vs S&P 500 · 6 meses", _to_float(rs.get("rs_6m")), "{:+.1f}%"),
    ]


def _niveles_clave(a) -> list:
    """[(etiqueta, texto)] de soporte / resistencia / nivel técnico, en llano."""
    kl = _rd(_rep(a, "technical")).get("key_levels") or {}
    out = []
    for key, label in (("support", "Soporte"), ("resistance", "Resistencia"),
                       ("stop_technical", "Nivel técnico de protección")):
        v = kl.get(key)
        if v:
            out.append((label, _limpiar(v)))
    return out


def _pills_future(a) -> list:
    km = _km(_rep(a, "future"))
    out = []
    moat = str(km.get("moat_strength") or "").lower()
    if not moat:      out.append(_pill_spec("VENTAJA COMPETITIVA", "—", SIN_DATO(), "Sin dato esta vez"))
    elif "wide" in moat:   out.append(_pill_spec("VENTAJA COMPETITIVA", "Amplia", BIEN(), "Difícil de copiar por los rivales"))
    elif "narrow" in moat: out.append(_pill_spec("VENTAJA COMPETITIVA", "Estrecha", REGULAR(), "Ventaja limitada: hay que vigilarla"))
    else:                  out.append(_pill_spec("VENTAJA COMPETITIVA", _enum_es(moat), MAL(), "Cualquiera puede competirle"))
    dr = str(km.get("disruption_risk") or "").lower()
    if not dr:         out.append(_pill_spec("RIESGO DE DISRUPCIÓN", "—", SIN_DATO(), "Sin dato esta vez"))
    elif "low" in dr:  out.append(_pill_spec("RIESGO DE DISRUPCIÓN", "Bajo", BIEN(), "Su negocio aguanta los cambios del sector"))
    elif "med" in dr:  out.append(_pill_spec("RIESGO DE DISRUPCIÓN", "Medio", REGULAR(), "Podría verse afectada por nuevas tecnologías"))
    else:              out.append(_pill_spec("RIESGO DE DISRUPCIÓN", "Alto", MAL(), "Podría quedarse atrás frente a rivales nuevos"))
    mq = str(km.get("management_quality") or "").lower()
    if not mq:                          out.append(_pill_spec("CALIDAD DIRECTIVA", "—", SIN_DATO(), "Sin dato esta vez"))
    elif "excel" in mq or "good" in mq: out.append(_pill_spec("CALIDAD DIRECTIVA", _enum_es(mq), BIEN(), "Los directivos usan bien el dinero"))
    elif "aver" in mq:                  out.append(_pill_spec("CALIDAD DIRECTIVA", "Media", REGULAR(), "Gestión correcta, sin destacar"))
    else:                               out.append(_pill_spec("CALIDAD DIRECTIVA", _enum_es(mq), MAL(), "Dudas sobre cómo se gestiona el capital"))
    bm = str(km.get("business_model") or "").lower()
    lect = {"platform": "Escala con costes bajos", "marketplace": "Conecta compradores y vendedores",
            "saas": "Ingresos recurrentes por suscripción", "traditional": "Negocio clásico: vende productos o servicios",
            "commodity": "Vende materia prima: depende del precio"}
    base = next((k for k in lect if k in bm), None)
    if not bm: out.append(_pill_spec("MODELO DE NEGOCIO", "—", SIN_DATO(), "Sin dato esta vez"))
    else:      out.append(_pill_spec("MODELO DE NEGOCIO", _enum_es(bm), INFO(), lect.get(base, "")))
    return out


def _pills_institutional(a) -> list:
    r = _rep(a, "institutional")
    km, rd = _km(r), _rd(r)
    hr = rd.get("holders_raw") if isinstance(rd.get("holders_raw"), dict) else {}
    out = []
    pct = _to_float(hr.get("institutional_ownership_pct"))
    if pct is None:
        mh = hr.get("major_holders_raw") if isinstance(hr.get("major_holders_raw"), dict) else {}
        vals = mh.get("Value") if isinstance(mh.get("Value"), dict) else {}
        f = _to_float(vals.get("institutionsPercentHeld"))
        pct = f * 100 if (f is not None and f <= 1.5) else f
    if pct is None:
        pct = _to_float(km.get("institutional_ownership"))
    if pct is None:   out.append(_pill_spec("PROPIEDAD INSTITUCIONAL", "—", SIN_DATO(), "Sin dato esta vez"))
    elif pct > 60:    out.append(_pill_spec("PROPIEDAD INSTITUCIONAL", f"{pct:.0f}%", BIEN(), "Los grandes fondos la respaldan"))
    elif pct >= 30:   out.append(_pill_spec("PROPIEDAD INSTITUCIONAL", f"{pct:.0f}%", REGULAR(), "Respaldo institucional moderado"))
    else:             out.append(_pill_spec("PROPIEDAD INSTITUCIONAL", f"{pct:.0f}%", MAL(), "Poco respaldo de los grandes fondos"))
    ins = str(km.get("insider_buying_signal") or "").lower()
    if not ins:          out.append(_pill_spec("DIRECTIVOS", "—", SIN_DATO(), "Sin dato esta vez"))
    elif "buy" in ins:   out.append(_pill_spec("DIRECTIVOS", "Comprando", BIEN(), "Los que más saben compran acciones"))
    elif "sell" in ins:  out.append(_pill_spec("DIRECTIVOS", "Vendiendo", MAL(), "Los directivos venden acciones"))
    else:                out.append(_pill_spec("DIRECTIVOS", "Neutral", REGULAR(), "Sin movimientos relevantes"))
    si = _to_float(km.get("short_interest"))
    if si is None:   out.append(_pill_spec("APUESTAS A LA BAJA", "—", SIN_DATO(), "Sin dato esta vez"))
    elif si < 3:     out.append(_pill_spec("APUESTAS A LA BAJA", f"{si:.1f}%", BIEN(), "Pocas apuestas en contra"))
    elif si <= 10:   out.append(_pill_spec("APUESTAS A LA BAJA", f"{si:.1f}%", REGULAR(), "Apuestas en contra moderadas"))
    else:            out.append(_pill_spec("APUESTAS A LA BAJA", f"{si:.1f}%", MAL(), "Muchas apuestas en contra"))
    sm = str(km.get("smart_money_signal") or "").lower()
    if not sm:                              out.append(_pill_spec("DINERO INTELIGENTE", "—", SIN_DATO(), "Sin dato esta vez"))
    elif "accum" in sm or "bull" in sm:     out.append(_pill_spec("DINERO INTELIGENTE", "Acumulando", BIEN(), "Los grandes inversores compran"))
    elif "distrib" in sm or "bear" in sm:   out.append(_pill_spec("DINERO INTELIGENTE", "Vendiendo", MAL(), "Los grandes inversores venden"))
    else:                                   out.append(_pill_spec("DINERO INTELIGENTE", "Neutral", REGULAR(), "Sin una dirección clara"))
    return out


def _dias_hasta(fecha_iso) -> int:
    try:
        d = datetime.fromisoformat(str(fecha_iso)[:10]).date()
        return (d - datetime.now().date()).days
    except Exception:
        return None


def _pills_catalysts(a) -> list:
    r = _rep(a, "catalysts")
    km, rd = _km(r), _rd(r)
    out = []
    nxt = rd.get("next_earnings") or km.get("next_earnings")
    fecha = str(nxt)[:10] if nxt else ""
    dias = _dias_hasta(fecha) if fecha else None
    fecha_es = _fecha_es(fecha) if fecha else ""
    if not fecha:      out.append(_pill_spec("PRÓXIMOS RESULTADOS", "—", SIN_DATO(), "Sin fecha confirmada"))
    elif dias is None: out.append(_pill_spec("PRÓXIMOS RESULTADOS", fecha_es, INFO(), "Fecha prevista"))
    elif dias < 0:     out.append(_pill_spec("PRÓXIMOS RESULTADOS", fecha_es, INFO(), "Ya publicados"))
    elif dias <= 30:   out.append(_pill_spec("PRÓXIMOS RESULTADOS", fecha_es, REGULAR("PRONTO"), f"En {dias} días: el precio puede moverse"))
    else:              out.append(_pill_spec("PRÓXIMOS RESULTADOS", fecha_es, INFO(), f"En {dias} días"))
    br = str(km.get("earnings_beat_rate") or "")
    m = re.search(r"(\d+)\s*/\s*(\d+)", br)
    if m and int(m.group(2)) > 0:
        p = int(m.group(1)) / int(m.group(2)) * 100
        if p >= 75:   out.append(_pill_spec("RACHA DE SORPRESAS", br.strip(), BIEN(), "Suele superar lo que espera el mercado"))
        elif p >= 50: out.append(_pill_spec("RACHA DE SORPRESAS", br.strip(), REGULAR(), "Resultados mixtos frente a lo esperado"))
        else:         out.append(_pill_spec("RACHA DE SORPRESAS", br.strip(), MAL(), "Suele decepcionar al mercado"))
    else:
        out.append(_pill_spec("RACHA DE SORPRESAS", "—", SIN_DATO(), "Sin historial de resultados"))
    sur = _to_float(km.get("avg_earnings_surprise"))
    if sur is None: out.append(_pill_spec("SORPRESA MEDIA", "—", SIN_DATO(), "Sin dato esta vez"))
    elif sur > 0:   out.append(_pill_spec("SORPRESA MEDIA", f"{sur:+.1f}%", BIEN(), "Gana más de lo que se esperaba"))
    elif sur < 0:   out.append(_pill_spec("SORPRESA MEDIA", f"{sur:+.1f}%", MAL(), "Gana menos de lo que se esperaba"))
    else:           out.append(_pill_spec("SORPRESA MEDIA", "0%", REGULAR(), "En línea con lo esperado"))
    tr = str(km.get("analyst_sentiment_trend") or "").lower()
    if not tr:             out.append(_pill_spec("ANALISTAS", "—", SIN_DATO(), "Sin dato esta vez"))
    elif "improv" in tr:   out.append(_pill_spec("ANALISTAS", "Mejorando", BIEN(), "Suben sus previsiones"))
    elif "deter" in tr:    out.append(_pill_spec("ANALISTAS", "Empeorando", MAL(), "Bajan sus previsiones"))
    else:                  out.append(_pill_spec("ANALISTAS", "Estable", REGULAR(), "Mantienen sus previsiones"))
    return out


def _pills_macro(a) -> list:
    r = _rep(a, "macro")
    km, rd = _km(r), _rd(r)
    snap = rd.get("macro_snapshot") if isinstance(rd.get("macro_snapshot"), dict) else {}
    out = []
    env = str(km.get("market_environment") or "").lower()
    if not env:          out.append(_pill_spec("ENTORNO DE MERCADO", "—", SIN_DATO(), "Sin dato esta vez"))
    elif "risk-on" in env or "risk on" in env: out.append(_pill_spec("ENTORNO DE MERCADO", "Apetito por el riesgo", BIEN(), "El mercado compra riesgo"))
    elif "risk-off" in env or "risk off" in env: out.append(_pill_spec("ENTORNO DE MERCADO", "Aversión al riesgo", MAL(), "El mercado huye del riesgo"))
    else:                out.append(_pill_spec("ENTORNO DE MERCADO", _enum_es(env), REGULAR(), "Sin una dirección clara"))
    rs = str(km.get("rate_sensitivity") or "").lower()
    if not rs:                              out.append(_pill_spec("TIPOS DE INTERÉS", "—", SIN_DATO(), "Sin dato esta vez"))
    elif "high" in rs and "neg" in rs:      out.append(_pill_spec("TIPOS DE INTERÉS", "Muy sensible", MAL(), "Las subidas de tipos le perjudican"))
    elif "high" in rs and "pos" in rs:      out.append(_pill_spec("TIPOS DE INTERÉS", "A favor", BIEN(), "Las subidas de tipos le ayudan"))
    elif "low" in rs or "neutral" in rs:    out.append(_pill_spec("TIPOS DE INTERÉS", "Poco sensible", BIEN(), "Los tipos apenas le afectan"))
    else:                                   out.append(_pill_spec("TIPOS DE INTERÉS", _enum_es(rs), REGULAR(), "Sensibilidad moderada a los tipos"))
    sm = str(km.get("sector_momentum") or "").lower()
    if not sm:            out.append(_pill_spec("IMPULSO DEL SECTOR", "—", SIN_DATO(), "Sin dato esta vez"))
    elif "strong" in sm:  out.append(_pill_spec("IMPULSO DEL SECTOR", "Fuerte", BIEN(), "Su sector está de moda"))
    elif "weak" in sm:    out.append(_pill_spec("IMPULSO DEL SECTOR", "Débil", MAL(), "El dinero sale de su sector"))
    else:                 out.append(_pill_spec("IMPULSO DEL SECTOR", "Neutral", REGULAR(), "Su sector no destaca"))
    vix_v = _to_float((snap.get("vix") or {}).get("current")) if isinstance(snap.get("vix"), dict) else None
    vl = str(km.get("vix_level") or "").lower()
    if vix_v is not None:
        val = f"{vix_v:.0f}"
        if vix_v < 20:   out.append(_pill_spec("NERVIOSISMO (VIX)", val, BIEN(), "Mercado tranquilo"))
        elif vix_v < 30: out.append(_pill_spec("NERVIOSISMO (VIX)", val, REGULAR(), "Mercado algo nervioso"))
        else:            out.append(_pill_spec("NERVIOSISMO (VIX)", val, MAL(), "Mercado muy nervioso"))
    elif vl:
        if "low" in vl:      out.append(_pill_spec("NERVIOSISMO (VIX)", "Bajo", BIEN(), "Mercado tranquilo"))
        elif "high" in vl:   out.append(_pill_spec("NERVIOSISMO (VIX)", "Alto", MAL(), "Mercado muy nervioso"))
        else:                out.append(_pill_spec("NERVIOSISMO (VIX)", "Elevado", REGULAR(), "Mercado algo nervioso"))
    else:
        out.append(_pill_spec("NERVIOSISMO (VIX)", "—", SIN_DATO(), "Sin dato esta vez"))
    return out


def _pills_sentiment(a) -> list:
    km = _km(_rep(a, "sentiment"))
    out = []
    s = str(km.get("overall_sentiment") or "").lower()
    if not s:           out.append(_pill_spec("SENTIMIENTO GENERAL", "—", SIN_DATO(), "Sin dato esta vez"))
    elif "bull" in s:   out.append(_pill_spec("SENTIMIENTO GENERAL", _enum_es(s), BIEN(), "El mercado habla bien de ella"))
    elif "bear" in s:   out.append(_pill_spec("SENTIMIENTO GENERAL", _enum_es(s), MAL(), "El mercado habla mal de ella"))
    else:               out.append(_pill_spec("SENTIMIENTO GENERAL", "Neutral", REGULAR(), "Ni euforia ni miedo"))
    m = str(km.get("sentiment_momentum") or "").lower()
    if not m:             out.append(_pill_spec("TENDENCIA DEL ÁNIMO", "—", SIN_DATO(), "Sin dato esta vez"))
    elif "improv" in m:   out.append(_pill_spec("TENDENCIA DEL ÁNIMO", "Mejorando", BIEN(), "Las noticias van a mejor"))
    elif "deter" in m:    out.append(_pill_spec("TENDENCIA DEL ÁNIMO", "Empeorando", MAL(), "Las noticias van a peor"))
    else:                 out.append(_pill_spec("TENDENCIA DEL ÁNIMO", "Estable", REGULAR(), "Sin cambios recientes"))
    nt = km.get("narrative_theme")
    out.append(_pill_spec("NARRATIVA DOMINANTE", _enum_es(nt) if nt else "—",
                          INFO() if nt else SIN_DATO(), "De qué habla el mercado"))
    cs = str(km.get("contrarian_signal") or "").lower()
    if not cs or "no signal" in cs or cs in ("none", "ninguna"):
        out.append(_pill_spec("SEÑAL CONTRARIA", "Sin señal", REGULAR(), "El ánimo no está en un extremo"))
    elif "fear" in cs or "miedo" in cs:
        out.append(_pill_spec("SEÑAL CONTRARIA", "Miedo", BIEN(), "El miedo del mercado crea oportunidad"))
    elif "hype" in cs or "greed" in cs or "eufor" in cs:
        out.append(_pill_spec("SEÑAL CONTRARIA", "Euforia", MAL(), "La euforia suele avisar de un techo"))
    else:
        out.append(_pill_spec("SEÑAL CONTRARIA", _enum_es(cs), INFO(), ""))
    return out


# ═════════════════════════════════════════════════════════════════════════
# Riesgo y precios
# ═════════════════════════════════════════════════════════════════════════
def _precios(a) -> dict:
    r = _rep(a, "risk")
    cr = _rd(r).get("computed_risk") if isinstance(_rd(r).get("computed_risk"), dict) else {}
    actual = _to_float(getattr(a, "entry_price", None)) or _to_float(cr.get("current_price"))
    stop = _to_float(getattr(a, "stop_loss", None)) or _to_float(cr.get("stop_suggested"))
    target = _to_float(getattr(a, "target_price", None)) or _to_float(cr.get("target_suggested"))
    down = (stop - actual) / actual * 100 if (actual and stop) else None
    up = (target - actual) / actual * 100 if (actual and target) else None
    return dict(actual=actual, stop=stop, target=target, down=down, up=up)


def _plan_posicion(a) -> list:
    """Filas (etiqueta, valor, Estado, lectura) del plan de la posición."""
    r = _rep(a, "risk")
    km = _km(r)
    cr = _rd(r).get("computed_risk") if isinstance(_rd(r).get("computed_risk"), dict) else {}
    p = _precios(a)
    rows = []
    rr_txt = _extract_ratio(getattr(a, "risk_reward", None) or km.get("risk_reward"), default=None)
    rr = _to_float(rr_txt.split(":")[0]) if rr_txt else _to_float(cr.get("rr_ratio"))
    if rr is None and p["up"] is not None and p["down"]:
        rr = abs(p["up"]) / abs(p["down"]) if p["down"] else None
    if rr is None:   rows.append(("Relación riesgo/beneficio", "—", SIN_DATO(), "Sin dato esta vez"))
    elif rr >= 2.5:  rows.append(("Relación riesgo/beneficio", f"{rr:.2f} : 1", BIEN(), f"Por cada $1 que arriesgas puedes ganar ${rr:.2f}"))
    elif rr >= 1.5:  rows.append(("Relación riesgo/beneficio", f"{rr:.2f} : 1", REGULAR(), f"Por cada $1 que arriesgas puedes ganar ${rr:.2f}"))
    else:            rows.append(("Relación riesgo/beneficio", f"{rr:.2f} : 1", MAL(), f"Ganas poco por cada $1 que arriesgas"))
    if p["down"] is not None:
        rows.append(("Pérdida máxima prevista", f"{p['down']:+.1f}%",
                     BIEN() if abs(p["down"]) <= 8 else REGULAR() if abs(p["down"]) <= 15 else MAL(),
                     "Hasta el nivel de protección"))
    else:
        rows.append(("Pérdida máxima prevista", "—", SIN_DATO(), "Sin dato esta vez"))
    if p["up"] is not None:
        rows.append(("Ganancia potencial", f"{p['up']:+.1f}%",
                     BIEN() if p["up"] >= 20 else REGULAR() if p["up"] >= 10 else MAL(),
                     "Hasta el precio objetivo"))
    else:
        rows.append(("Ganancia potencial", "—", SIN_DATO(), "Sin dato esta vez"))
    ps = _to_float(getattr(a, "position_size_pct", None) or km.get("position_size_pct"))
    if ps is None: rows.append(("Tamaño de posición sugerido", "—", SIN_DATO(), "Sin dato esta vez"))
    else:          rows.append(("Tamaño de posición sugerido", f"{ps:.1f}%", INFO(), "De tu cartera, como máximo"))
    texto, est = _verdict_asymmetry(getattr(a, "asymmetry_direction", None),
                                    getattr(a, "asymmetry_strength", None))
    rows.append(("Asimetría", texto, est, "Lo que puedes ganar frente a lo que puedes perder"))
    return rows


# ═════════════════════════════════════════════════════════════════════════
# Tesis y textos del veredicto
# ═════════════════════════════════════════════════════════════════════════
def _tesis_parrafos(a) -> list:
    t = _limpiar(getattr(a, "investment_thesis", "") or "")
    if not t:
        return []
    partes = [p.strip() for p in re.split(r"\n{2,}|\n", t) if p.strip()]
    return partes[:2] if partes else []


def _horizonte(a) -> str:
    h = _limpiar(getattr(a, "time_horizon", "") or "")
    if not h:
        return "Largo plazo (años)"
    corto = re.split(r"\s+[—–-]\s+|:|\.|;|\(|,", h, maxsplit=1)[0].strip()
    if len(corto) > 30:
        corto = corto[:30].rsplit(" ", 1)[0].rstrip(" ,;")
    return corto if corto else "Largo plazo (años)"


def _fecha_es(iso) -> str:
    try:
        return datetime.fromisoformat(str(iso)).strftime("%d/%m/%Y")
    except Exception:
        return str(iso or "")[:10]
