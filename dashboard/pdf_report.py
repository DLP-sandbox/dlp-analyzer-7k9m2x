"""
dashboard/pdf_report.py — Informe DLP en PDF (fachada).

Genera un informe de 3 páginas landscape 16:9 (1920×1080 pt), pensado para que
un principiante lo lea UNA vez y lo entienda, con navegación clicable e índice:
  1. Veredicto    — quién es la empresa, el puntaje, dos gráficas y «en pocas palabras»
  2. El negocio   — 3 datos con semáforo y frase SIN cifras, los pilares y la lectura
  3. El momento   — 3 datos, el recorrido del precio, la lectura y el Club DLP
Las frases «en pocas palabras» las escribe la IA en el análisis (campo
`en_pocas_palabras`) y se imprimen solo si no traen ninguna cifra; si faltan o
traen números, se generan por reglas. Ninguna frase del informe lleva datos: el
número va arriba y la frase explica qué significa.

Garantías del módulo:
  · CERO llamadas a Anthropic. Ni este módulo ni pdf_theme / pdf_rules /
    pdf_charts / pdf_vector / pdf_pages importan anthropic, instancian
    Orchestrator ni tocan client.messages. Verificable:
        grep -nE "anthropic|client\\.messages|Orchestrator" dashboard/pdf_*.py
  · CERO binarios externos. Las cuatro gráficas se dibujan en vector con
    ReportLab (dashboard/pdf_vector.py), no con Plotly + kaleido: aquel
    rasterizador arranca un Chromium que en Streamlit Cloud no tiene sus
    librerías del sistema, fallaba, y el PDF salía con el texto completo y sin
    una sola gráfica. Ahora el informe se ve idéntico en local y en la nube.
"""
import io

from reportlab.pdfgen import canvas

from dashboard.pdf_theme import PAGE_W, PAGE_H, FONT_REG
from dashboard.pdf_rules import SECCIONES
from dashboard.pdf_pages import PAGINAS

# Re-exportados por compatibilidad con scripts y pruebas anteriores.
from dashboard.pdf_charts import (  # noqa: F401
    _styled_logo_png, _logo_directo, _autodetect_logo, LOGO_PATH,
)
from dashboard.pdf_vector import (  # noqa: F401
    dibujar_medidor, dibujar_radar, dibujar_precio, dibujar_qr,
)


def build_analysis_pdf(analysis) -> bytes:
    """Genera el informe de 3 páginas y devuelve los bytes del PDF."""
    buf = io.BytesIO()
    try:
        # Fuente inicial de marca: así ninguna página declara Helvetica.
        c = canvas.Canvas(buf, pagesize=(PAGE_W, PAGE_H), initialFontName=FONT_REG)
    except TypeError:
        c = canvas.Canvas(buf, pagesize=(PAGE_W, PAGE_H))
    ticker = str(getattr(analysis, "ticker", "") or "")
    c.setTitle(f"Informe DLP — {ticker}")
    c.setAuthor("Diario Largo Plazo · DLP Market Analyzer")
    c.setSubject(f"Análisis de {ticker} para invertir a largo plazo")
    c.setKeywords(f"DLP, Club DLP, {ticker}, análisis, inversión, largo plazo")
    c.setCreator("DLP Market Analyzer")

    for sec, pagina in zip(SECCIONES, PAGINAS):
        pagina(c, analysis)
        c.addOutlineEntry(f"{sec['n']}. {sec['titulo'].title()}", f"pg{sec['n']}", level=0)
        c.showPage()

    c.showOutline()
    c.save()
    return buf.getvalue()
