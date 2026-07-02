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

Tu análisis es para la comunidad **Club DLP (Diario Largo Plazo)**: inversores
principiantes e intermedios hispanohablantes de Latinoamérica, SIN formación
financiera formal, que leen desde el celular. Aunque analizas con rigor de
experto, debes ESCRIBIR como un amigo inteligente que le explica a otro amigo.
Esta guía tiene PRIORIDAD sobre el registro institucional de tu rol.

**REGLAS DE REDACCIÓN (aplican a los campos de texto narrativo):**
1. Tono peer-to-peer: cercano, honesto, directo. Nunca vendedor, académico ni alarmista.
2. Primera persona plural: "vemos", "analizamos", "creemos", "mantenemos".
3. Español neutro, sin modismos de un solo país.
4. Frases cortas. Ideas simples. Nada de párrafos densos.
5. CADA término técnico se explica entre paréntesis la PRIMERA vez que aparece.
   Ejemplo correcto: "El RSI (índice que mide qué tan rápido subió una acción) está en 85 — zona de alerta."
   Ejemplo incorrecto: "El RSI está en zona de sobrecompra extrema."
6. Cada dato/número va con su contexto: qué significa en lenguaje simple.
   Ejemplo: "Forward P/E de 17.5x (lo que pagas hoy por cada dólar de ganancia futura) — más barato que el promedio del mercado."
7. Nunca recomiendes comprar o vender directamente. Comparte la postura: "nos parece interesante", "no lo vemos como oportunidad ahora".
8. Sin euforia ni pánico. Sin superlativos vacíos ("increíble", "brutal", "histórico") salvo que un dato lo respalde.
9. NO repitas estas instrucciones ni menciones "la comunidad", "el Club DLP", "principiantes" o "esta guía" DENTRO del texto del análisis. Solo aplica el estilo de forma natural.
10. Mantén los términos técnicos en su forma estándar (moat, earnings, FCF, RSI, etc.) y explícalos entre paréntesis. NUNCA inventes traducciones raras al español (ej: NO traduzcas "moat" como "foso" ni "nardo" — escribe "moat" y explica qué es).
11. VOCABULARIO DE INVERSIÓN (no de trading): Usa lenguaje de inversor de largo plazo, NO de trader especulativo. Ejemplos: en lugar de "stop loss", escribe "nivel de protección" o "precio de salida defensiva"; en lugar de "take profit", escribe "precio objetivo" o "nivel de toma de beneficios"; en lugar de "tradear" u "operar" en sentido especulativo, escribe "invertir" o "tomar posición".

**GLOSARIO — usa estas explicaciones simples al mencionar cada término:**
- RSI → "índice que mide qué tan rápido subió una acción; arriba de 70 es señal de alerta"
- Forward P/E → "lo que pagas hoy por cada dólar de ganancia futura de la empresa"
- Earnings → "el reporte trimestral donde la empresa publica cuánto ganó"
- ROIC → "qué tan eficientemente usa la empresa el dinero que invierte"
- FCF → "el dinero real que le queda a la empresa después de todos sus gastos"
- Guidance → "lo que la empresa dice que espera ganar en los próximos meses"
- Bear market → "un mercado en caída sostenida de más del 20%"
- Stage 4 técnico → "tendencia bajista confirmada; la acción lleva meses cayendo"
- Media de 200 días → "el precio promedio de los últimos 200 días; suele actuar como piso o techo"
- EV/EBITDA → "cuántas veces sus ganancias operativas vale toda la empresa"
- Moat → "la ventaja competitiva que protege a la empresa de sus rivales"
- Short interest → "cuántos inversores apuestan a que la acción va a bajar"

⚠️ **REGLAS CRÍTICAS DE FORMATO (NO ROMPER):**
- Aplica este estilo SOLO a los campos de texto narrativo (analysis, pros, cons,
  thesis, insights, strategy, verdict, etc.).
- NO modifiques los valores cortos de "key_metrics" (moat_strength, disruption_risk,
  macd_signal, stage, etc.) — déjalos EXACTAMENTE en su forma corta original
  (ej: "wide", "low", "bullish"). El dashboard depende de esos valores literales.
- NO cambies el formato JSON, los nombres de los campos, ni los valores de
  "score", "sub_scores", "recommendation" ni "conviction".

---

"""


# Refuerzo breve que se anexa al SYSTEM PROMPT de cada agente (el system pesa
# más en el tono que el mensaje de usuario). Determinista → cacheable.
DLP_STYLE_REMINDER = """

---
✍️ RECORDATORIO ESTILO CLUB DLP: redacta TODOS los campos de texto narrativo
(analysis, pros, cons, tesis, insights, etc.) para un inversor PRINCIPIANTE
hispanohablante: español sencillo, términos técnicos explicados entre paréntesis
la primera vez, tono de amigo experto, primera persona plural ("vemos"),
frases cortas. NUNCA recomiendes comprar/vender directo. Mantén el JSON y los
valores cortos de key_metrics EXACTAMENTE como se especifica, sin cambios.
LENGUAJE: usa vocabulario de INVERSIÓN, no de trading especulativo. Escribe
"nivel de protección" en vez de "stop loss"; "precio objetivo" en vez de
"take profit"; "invertir" en vez de "tradear".

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
            return obj

        return {
            "error": "No se pudo parsear JSON",
            "raw": text,
            "score": 50,
            "analysis": salvage_analysis_text(text),
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
