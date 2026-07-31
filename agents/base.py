"""
Clase base para todos los sub-agentes. Define el contrato de análisis
y la interfaz con el Claude API usando prompt caching.
"""
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Optional

import anthropic

from config.settings import SUBAGENT_MODEL, MAX_TOKENS_AGENT


# ── Contexto temporal — inyectado en cada llamada a Claude ──────────────
SPANISH_DAYS = {
    "Monday": "lunes", "Tuesday": "martes", "Wednesday": "miércoles",
    "Thursday": "jueves", "Friday": "viernes", "Saturday": "sábado", "Sunday": "domingo",
}
SPANISH_MONTHS = {
    "January": "enero", "February": "febrero", "March": "marzo", "April": "abril",
    "May": "mayo", "June": "junio", "July": "julio", "August": "agosto",
    "September": "septiembre", "October": "octubre", "November": "noviembre", "December": "diciembre",
}


def today_context() -> str:
    """
    Construye el header de contexto temporal que se inyecta a TODOS los agentes.
    Garantiza que cada análisis sepa exactamente la fecha y hora actual,
    para que priorice información reciente y evalúe correctamente eventos futuros.
    También adjunta la Guía de Redacción Club DLP (DLP_STYLE_GUIDE).
    """
    now = datetime.now()
    day_en = now.strftime("%A")
    month_en = now.strftime("%B")
    day_es = SPANISH_DAYS.get(day_en, day_en)
    month_es = SPANISH_MONTHS.get(month_en, month_en)

    date_str = f"{day_es}, {now.day} de {month_es} de {now.year}"
    iso_date = now.strftime("%Y-%m-%d")
    time_str = now.strftime("%H:%M")

    tomorrow = (now + timedelta(days=1)).strftime("%Y-%m-%d")
    in_2_days = (now + timedelta(days=2)).strftime("%Y-%m-%d")
    in_1_week = (now + timedelta(days=7)).strftime("%Y-%m-%d")
    in_2_weeks = (now + timedelta(days=14)).strftime("%Y-%m-%d")
    in_1_month = (now + timedelta(days=30)).strftime("%Y-%m-%d")

    quarter = (now.month - 1) // 3 + 1

    # Próxima sesión hábil (saltando fines de semana)
    next_session = now + timedelta(days=1)
    while next_session.weekday() >= 5:
        next_session += timedelta(days=1)
    next_session_str = next_session.strftime("%Y-%m-%d (%A)")

    is_weekend = now.weekday() >= 5
    market_status = "🔴 MERCADO CERRADO (fin de semana)" if is_weekend else "🟢 MERCADO HÁBIL"

    return f"""## ⏱ CONTEXTO TEMPORAL — REFERENCIA OBLIGATORIA

**FECHA Y HORA ACTUAL DE LA CONSULTA:**
- Fecha: **{date_str}**
- ISO: **{iso_date}**
- Hora: {time_str}
- Trimestre fiscal: **Q{quarter} {now.year}**
- Estado del mercado US: {market_status}

**FECHAS FUTURAS DE REFERENCIA:**
- Próxima sesión hábil: {next_session_str}
- Mañana: {tomorrow}
- En 2 días: {in_2_days}
- En 1 semana: {in_1_week}
- En 2 semanas: {in_2_weeks}
- En 1 mes: {in_1_month}

⚠️ **INSTRUCCIONES TEMPORALES OBLIGATORIAS:**
1. Toda tu análisis debe entenderse como ACTUAL al {iso_date}.
2. PRIORIZA siempre la información más reciente sobre la histórica.
3. Para eventos futuros (earnings, catalizadores, lanzamientos), calcula días/semanas desde HOY ({iso_date}).
4. Si detectas datos antiguos o desactualizados, MENCIÓNALO explícitamente en tu análisis.
5. Tu conocimiento puede tener corte anterior — confía en los DATOS provistos como verdad actual.
6. Evalúa el horizonte temporal: ¿este evento es inminente (<7d), cercano (<30d) o lejano (>30d)?

---

{DLP_STYLE_GUIDE}
"""


# ── Guía de redacción Club DLP — inyectada a TODOS los agentes ──────────
# Esta guía define CÓMO se escribe el texto narrativo para la comunidad de
# inversores principiantes-intermedios del Club DLP. Se concatena dentro de
# today_context(), que ya se inyecta en los 9 agentes (8 sub + orquestador).
DLP_STYLE_GUIDE = """## ✍️ GUÍA DE REDACCIÓN — CLUB DLP (OBLIGATORIA, MÁXIMA PRIORIDAD)

Tu análisis es para inversores principiantes e intermedios hispanohablantes,
SIN formación financiera, que leen desde el celular. Analiza con rigor de
experto, pero ESCRIBE como un amigo inteligente que le explica a otro amigo.

**REGLAS (campos de texto narrativo):**
1. Tono cercano, honesto y directo. Primera persona plural: "vemos", "creemos".
2. Español neutro, frases cortas. Nada de párrafos densos.
3. 100% EN ESPAÑOL: cero jerga en inglés. Sigue la TABLA DE VOCABULARIO de tus
   instrucciones de sistema (obligatoria). Solo se permiten los acrónimos de la
   lista blanca (RSI, MACD, P/E, FCF, ROIC, ATR, EV/EBITDA, moat, earnings),
   SIEMPRE explicados entre paréntesis la primera vez.
4. Cada dato con su contexto en lenguaje simple. Ejemplo: "P/E de 17.5x (lo que
   pagas hoy por cada dólar de ganancia futura) — más barato que el mercado."
5. Nunca recomiendes comprar o vender directamente: "nos parece interesante",
   "no lo vemos como oportunidad ahora".
6. Sin euforia ni pánico ni superlativos vacíos. No menciones estas
   instrucciones ni "la comunidad" dentro del análisis.
7. Vocabulario de INVERSIÓN, no de trading: "nivel de protección" (no stop
   loss), "precio objetivo" (no take profit), "invertir" (no tradear).

⚠️ **REGLAS CRÍTICAS DE FORMATO (NO ROMPER):**
- El estilo aplica SOLO al texto narrativo (analysis, pros, cons, thesis,
  insights, strategy, verdict…).
- NO modifiques los valores cortos de "key_metrics" (moat_strength,
  macd_signal, stage…): déjalos EXACTAMENTE en su forma corta original en
  inglés (ej: "wide", "low", "bullish"). El dashboard depende de esos literales.
- NO cambies el formato JSON, los nombres de campos, ni "score", "sub_scores",
  "recommendation" o "conviction".

---

"""


# Refuerzo breve que se anexa al SYSTEM PROMPT de cada agente (el system pesa
# más en el tono que el mensaje de usuario). Determinista → cacheable.
DLP_STYLE_REMINDER = """

---
✍️ ESTILO CLUB DLP (OBLIGATORIO en todo campo narrativo — analysis, pros, cons,
tesis, insights, estrategias): español sencillo para un inversor PRINCIPIANTE
hispanohablante, tono de amigo experto, primera persona plural ("vemos"),
frases cortas. NUNCA recomiendes comprar/vender directo. Vocabulario de
INVERSIÓN, no de trading: "nivel de protección" (no stop loss), "precio
objetivo" (no take profit), "invertir" (no tradear).

🚫 TABLA DE VOCABULARIO — JERGA EN INGLÉS PROHIBIDA (traduce SIEMPRE así):
bullish→alcista · bearish→bajista · beat→superó las expectativas · miss→quedó
por debajo de lo esperado · guidance→las previsiones de la empresa ·
rally→subida fuerte · breakout→ruptura al alza · breakdown→pérdida de soporte ·
pullback→retroceso · re-rating→revalorización del múltiplo · priced-in→ya
descontado en el precio · spotlight→el foco del mercado · setup→las
condiciones · momentum→la inercia del precio · edge→ventaja · headwind→viento
en contra · tailwind→viento a favor · top line→los ingresos · bottom line→la
ganancia final · profit-taking→toma de beneficios · sell-off→ola de ventas ·
turnaround→recuperación del negocio · risk-on/risk-off→apetito/aversión al
riesgo · drawdown→caída desde máximos · float→acciones en circulación ·
crowded trade→apuesta masificada · hold→mantener (un "hold LP" es "mantener a
largo plazo") · beats→trimestres batiendo expectativas · overbought→sobrecompra
· oversold→sobreventa.
Si un término en inglés no está aquí, TRADÚCELO igual: la regla es que el texto
narrativo se lea 100% en español natural. OJO con los plurales y compuestos
("8 beats", "earnings beats"): también van en español.

✅ LISTA BLANCA (únicos términos que se conservan, SIEMPRE explicados entre
paréntesis la primera vez): RSI, MACD, P/E, FCF, ROIC, ATR, EV/EBITDA, moat
("la ventaja competitiva que la protege"), earnings ("el reporte trimestral de
resultados"), compounder ("empresa que multiplica su valor año tras año").
No inventes traducciones raras de estos (moat NO es "foso").

📐 ESTRUCTURA DE VALOR (misma longitud, más sustancia):
- Cada `analysis`: qué vemos (el dato) → qué significa para ti (la lectura en
  llano) → qué vigilar (la señal concreta que lo cambiaría).
- Cada pro/con: el dato + POR QUÉ le importa a un inversor de largo plazo, en
  una frase completa. Nada de telegramas ni cifras sueltas sin lectura.

⚠️ FORMATO: mantén el JSON y los valores cortos de key_metrics EXACTAMENTE como
se especifica (en inglés: "wide", "bullish", "low"…) — el dashboard depende de
esos literales. El español aplica SOLO al texto narrativo.

🎯 SCORING ANTI-CLUSTERING (REGLA CRÍTICA):
NO uses scores típicos de banda (72, 65, 80, 50). Da scores PRECISOS con granularidad
de 1-3 puntos basados en evidencia cuantitativa real. Cada análisis es único: dos empresas
nunca tienen exactamente el mismo perfil. Si dudas entre 70 y 75, usa 71, 73, 74 según
qué tan cerca esté la evidencia de uno u otro extremo. Evita repetir 72, 75, 80 entre
análisis distintos. Calibra a la baja: 60 no es "promedio", es "mediocre"; 75 no es
"bueno", es "muy bueno claramente por encima del sector"; 85 es excepcional. Usa toda
la escala 30-95 con precisión decimal-style (aunque enteros), no te encajones en bandas."""


@dataclass
class AgentReport:
    agent_name: str
    score: float                        # 0–100
    analysis: str                       # Análisis narrativo detallado
    pros: list[str] = field(default_factory=list)
    cons: list[str] = field(default_factory=list)
    key_metrics: dict[str, Any] = field(default_factory=dict)
    conviction: str = "MEDIUM"          # HIGH / MEDIUM / LOW
    sub_scores: dict[str, float] = field(default_factory=dict)
    raw_data: dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None

    def to_dict(self) -> dict:
        return {
            "agent_name":  self.agent_name,
            "score":       self.score,
            "analysis":    self.analysis,
            "pros":        self.pros,
            "cons":        self.cons,
            "key_metrics": self.key_metrics,
            "conviction":  self.conviction,
            "sub_scores":  self.sub_scores,
            "raw_data":    self.raw_data,
            "error":       self.error,
        }


# ── Parseo robusto de JSON de las respuestas de Claude ──────────────────
# Los modelos (sobre todo Haiku) suelen escribir los campos narrativos con
# SALTOS DE LÍNEA LITERALES dentro del string (ej: "analysis" en 1-2 párrafos).
# json.loads en modo estricto rechaza esos caracteres de control ("Invalid
# control character"), lo que hacía fallar el parseo y volcar el JSON crudo en
# pantalla. Estas utilidades toleran esos casos y reparan JSON truncado, sin
# cambiar el comportamiento para respuestas ya válidas.

def _close_truncated_json(s: str) -> str:
    """Cierra strings/objetos/arrays que quedaron abiertos por truncado."""
    in_str = False
    esc = False
    stack = []
    for ch in s:
        if esc:
            esc = False
            continue
        if ch == "\\":
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch in "{[":
            stack.append(ch)
        elif ch == "}" and stack and stack[-1] == "{":
            stack.pop()
        elif ch == "]" and stack and stack[-1] == "[":
            stack.pop()
    out = s
    if in_str:
        out += '"'
    out = re.sub(r",\s*$", "", out.rstrip())
    for ch in reversed(stack):
        out += "}" if ch == "{" else "]"
    return out


def _lenient_json_loads(s: str):
    """json.loads tolerante: permite saltos de línea literales (strict=False),
    quita comas colgantes y repara truncados. Devuelve dict o None."""
    s = s.strip()
    no_trailing = re.sub(r",(\s*[}\]])", r"\1", s)
    for cand in (s, no_trailing, _close_truncated_json(s), _close_truncated_json(no_trailing)):
        try:
            obj = json.loads(cand, strict=False)
        except Exception:
            continue
        if isinstance(obj, dict):
            return obj
    return None


def _first_balanced_object(text: str):
    """Devuelve el primer objeto JSON balanceado (respeta strings). Si quedó
    truncado, devuelve desde la primera '{' hasta el final para repararlo luego."""
    start = text.find("{")
    if start == -1:
        return None
    in_str = False
    esc = False
    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if esc:
            esc = False
            continue
        if ch == "\\":
            esc = True
            continue
        if ch == '"':
            in_str = not in_str
            continue
        if in_str:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return text[start:]


def extract_json_dict(text: str):
    """Extrae de forma robusta el primer objeto JSON de `text`. dict o None."""
    candidates = []
    m = re.search(r"```(?:json)?\s*([\s\S]+?)```", text)
    if m:
        candidates.append(m.group(1))
    balanced = _first_balanced_object(text)
    if balanced:
        candidates.append(balanced)
    m = re.search(r"\{[\s\S]+\}", text)
    if m:
        candidates.append(m.group(0))
    for cand in candidates:
        obj = _lenient_json_loads(cand)
        if obj is not None:
            return obj
    return None


def salvage_analysis_text(text: str) -> str:
    """Rescata SÓLO el texto del campo 'analysis' de un JSON irrecuperable.
    Nunca devuelve el JSON crudo: si no hay nada rescatable, un mensaje limpio."""
    m = re.search(r'"analysis"\s*:\s*"((?:[^"\\]|\\.)*)"', text, re.DOTALL)
    if m:
        try:
            val = json.loads('"' + m.group(1) + '"', strict=False).strip()
            if len(val) >= 20:
                return val
        except Exception:
            pass
    # Truncado: desde "analysis": " hasta el próximo campo o el final del texto
    m = re.search(r'"analysis"\s*:\s*"(.+?)(?="\s*,\s*"\w+"\s*:|"\s*\}|$)', text, re.DOTALL)
    if m:
        val = re.sub(r"\\[nrt]", " ", m.group(1))
        val = val.replace('\\"', '"').replace("\\", "").strip().strip('"').strip()
        if len(val) >= 20:
            return val
    return ("No pudimos generar la conclusión de este análisis en este intento. "
            "Vuelve a ejecutarlo en un momento; a veces la fuente de datos o el "
            "modelo tardan en responder.")


# ── Red de seguridad de idioma (determinista, cero tokens) ────────────────
# El prompt pide español natural, pero Haiku a veces deja caer jerga en inglés
# igual ("8 beats consecutivos", "upside", "guidance"). Esta capa la traduce en
# CÓDIGO justo después del parseo: garantiza el resultado sin depender del
# modelo y sin gastar un token. Solo toca los CAMPOS NARRATIVOS del allowlist —
# jamás key_metrics, sub_scores, enums ni claves del JSON.

_JERGA_ES = [
    # (patrón con límites de palabra, reemplazo). Orden: compuestos primero.
    (r"short interest", "apuestas bajistas"),
    (r"short squeeze", "estrangulamiento de cortos"),
    (r"crowded trade", "apuesta masificada"),
    (r"track record", "historial"),
    (r"setups?", "condiciones"),
    (r"squeezes?", "estrangulamiento de cortos"),
    (r"edges?", "ventaja"),
    (r"profit[- ]taking", "toma de beneficios"),
    (r"priced[- ]in", "ya descontado en el precio"),
    (r"re[- ]?rating", "revalorización del múltiplo"),
    (r"risk[- ]on", "apetito de riesgo"),
    (r"risk[- ]off", "aversión al riesgo"),
    (r"sell[- ]?off", "ola de ventas"),
    (r"top[- ]line", "los ingresos"),
    (r"bottom[- ]line", "la ganancia final"),
    (r"earnings beats?", "resultados por encima de lo esperado"),
    (r"beats", "resultados por encima de lo esperado"),
    (r"beat", "resultado por encima de lo esperado"),
    (r"misses", "resultados por debajo de lo esperado"),
    (r"miss", "resultado por debajo de lo esperado"),
    (r"bullish", "alcista"),
    (r"bearish", "bajista"),
    (r"guidance", "previsiones de la empresa"),
    (r"rally", "subida fuerte"),
    (r"breakout", "ruptura al alza"),
    (r"breakdown", "pérdida de soporte"),
    (r"pullback", "retroceso"),
    (r"spotlight", "foco del mercado"),
    (r"momentum", "inercia del precio"),
    (r"upside", "potencial de subida"),
    (r"downside", "riesgo de caída"),
    (r"underperform(?:ance|ando|ing)?", "rendimiento por debajo del mercado"),
    (r"outperform(?:ance|ando|ing)?", "rendimiento por encima del mercado"),
    (r"headwinds?", "vientos en contra"),
    (r"tailwinds?", "vientos a favor"),
    (r"drawdowns?", "caídas desde máximos"),
    (r"turnaround", "recuperación del negocio"),
    (r"overbought", "sobrecompra"),
    (r"oversold", "sobreventa"),
    (r"float", "acciones en circulación"),
    (r"hold LP", "mantener a largo plazo"),
    (r"hold", "mantener"),
]
_JERGA_RX = [(re.compile(r"(?<![A-Za-z\-])" + p + r"(?![A-Za-z\-])", re.IGNORECASE), r)
             for p, r in _JERGA_ES]

# Campos narrativos donde SÍ se traduce. Todo lo demás (key_metrics, enums,
# scores, claves) queda intacto.
_CAMPOS_NARRATIVOS = {
    "analysis", "pros", "cons", "investment_thesis", "key_strengths",
    "key_risks", "entry_strategy", "exit_strategy", "alpha_opportunity",
    "time_horizon", "key_insight", "dominant_narrative", "opportunity",
    "macro_verdict", "top_catalyst", "entry_setup", "stop_rationale",
    "dcf_thesis", "earnings_quality_note", "future_thesis", "verdict",
    "upcoming_events", "recent_material_events",
}


def _traducir_texto(t: str) -> str:
    for rx, rep in _JERGA_RX:
        t = rx.sub(rep, t)
    return t


def es_natural(obj, _en_narrativo: bool = False):
    """Recorre el JSON parseado y traduce la jerga SOLO en campos narrativos.
    Nunca lanza; ante cualquier duda devuelve el valor original."""
    try:
        if isinstance(obj, dict):
            return {k: es_natural(v, _en_narrativo or (k in _CAMPOS_NARRATIVOS))
                    for k, v in obj.items()}
        if isinstance(obj, list):
            return [es_natural(v, _en_narrativo) for v in obj]
        if isinstance(obj, str) and _en_narrativo:
            return _traducir_texto(obj)
        return obj
    except Exception:
        return obj


def _looks_like_leaked_json(text: str) -> bool:
    """True SÓLO si el texto es claramente un volcado de JSON crudo (no prosa).

    Conservador a propósito: una conclusión normal en español nunca empieza con
    '{' o '```', ni contiene la clave literal `"analysis":`. Así es imposible
    tocar por error un análisis bien formado."""
    if not text:
        return False
    stripped = text.lstrip()
    if stripped.startswith("{") or stripped.startswith("```"):
        return True
    # Clave JSON literal de un reporte serializado (el key va en inglés; la
    # prosa en español usaría «análisis» con tilde, nunca `"analysis":`).
    return re.search(r'"(analysis|score|conviction)"\s*:', text) is not None


def sanitize_leaked_json_text(text: str) -> str:
    """Si `text` es un JSON crudo filtrado (bug de análisis viejos guardados),
    devuelve SÓLO la conclusión limpia. Si es prosa normal, lo deja intacto.

    No muta datos: se aplica al cargar/mostrar, extrayendo el texto real sobre
    la marcha. Para texto ya limpio es un no-op."""
    if not isinstance(text, str) or not _looks_like_leaked_json(text):
        return text
    obj = extract_json_dict(text)
    if obj is not None:
        val = obj.get("analysis")
        if isinstance(val, str) and val.strip():
            return val.strip()
    return salvage_analysis_text(text)


class BaseAgent:
    name: str = "BaseAgent"
    model: str = SUBAGENT_MODEL

    def __init__(self, client: anthropic.Anthropic):
        self.client = client

    def analyze(self, ticker: str, data: dict) -> AgentReport:
        raise NotImplementedError

    def _call_claude(self, system_prompt: str, user_message: str, max_tokens: int = MAX_TOKENS_AGENT) -> dict:
        """Llama a Claude y parsea la respuesta JSON.
        Inyecta contexto temporal + guía de estilo DLP automáticamente:
        - today_context() (que incluye DLP_STYLE_GUIDE) al inicio del user message
        - DLP_STYLE_REMINDER al final del system prompt (refuerzo cacheable)."""
        try:
            full_user_message = today_context() + user_message
            response = self.client.messages.create(
                model=self.model,
                max_tokens=max_tokens,
                system=[
                    {
                        "type": "text",
                        "text": system_prompt + DLP_STYLE_REMINDER,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                messages=[{"role": "user", "content": full_user_message}],
            )
            raw = response.content[0].text
            return self._parse_json(raw)
        except Exception as e:
            return {"error": str(e), "score": 50, "analysis": f"Error en análisis: {e}", "pros": [], "cons": []}

    def _parse_json(self, text: str) -> dict:
        """Extrae el primer bloque JSON de la respuesta de forma robusta.
        Tolera saltos de línea literales dentro de los strings y repara JSON
        truncado. Si aun así no se puede parsear, rescata SÓLO el texto del
        campo `analysis` — NUNCA vuelca el JSON crudo en pantalla."""
        obj = extract_json_dict(text)
        if obj is not None:
            # Red de seguridad de idioma: traduce la jerga inglesa que el
            # modelo haya dejado caer en los campos narrativos. Determinista y
            # sin tokens; key_metrics/enums quedan intactos.
            return es_natural(obj)

        return {
            "error": "No se pudo parsear JSON",
            "raw": text,
            "score": 50,
            "analysis": _traducir_texto(salvage_analysis_text(text)),
            "pros": [],
            "cons": [],
        }

    def _format_number(self, value, decimals: int = 2, suffix: str = "") -> str:
        if value is None:
            return "N/A"
        if abs(value) >= 1e9:
            return f"${value/1e9:.1f}B{suffix}"
        if abs(value) >= 1e6:
            return f"${value/1e6:.1f}M{suffix}"
        return f"{value:.{decimals}f}{suffix}"

    def _safe_report(self, ticker: str, error: str) -> AgentReport:
        return AgentReport(
            agent_name=self.name,
            score=50,
            analysis=("No pudimos completar esta parte del análisis porque faltaron "
                      "datos suficientes. Te recomendamos volver a intentarlo en un "
                      "momento; a veces la fuente de datos tarda en responder."),
            pros=[],
            cons=["Por ahora no tenemos datos suficientes para sacar conclusiones aquí"],
            conviction="LOW",
            error=error,
        )
