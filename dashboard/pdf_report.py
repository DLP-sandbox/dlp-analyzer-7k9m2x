"""
dashboard/pdf_report.py — Informe DLP en PDF (fachada).

Genera un informe de 7 páginas landscape 16:9 (1920×1080 pt) con navegación
clicable e índice del lector:
  1. Veredicto      — hero, medidor, perfil, desglose nativo, tesis, precios
  2. Fundamentales  — seis métricas con semáforo y frase, pilares, señales
  3. Técnico        — tendencia, etapa/RSI/MACD/máximo anual, frente al mercado
  4. Futuro + Smart Money
  5. Contexto       — catalizadores, macro, sentimiento
  6. Riesgo         — recorrido del precio, niveles, plan de la posición
  7. Conclusión     — a favor / en contra, entrada y salida, Club DLP

Garantía: CERO llamadas a Anthropic. Ni este módulo ni pdf_theme / pdf_rules /
pdf_charts / pdf_pages importan anthropic, instancian Orchestrator ni tocan
client.messages. Solo leen el StockAnalysis ya construido y dibujan. Verificable:
    grep -nE "anthropic|client\\.messages|Orchestrator" dashboard/pdf_*.py
"""
import io

from reportlab.pdfgen import canvas

from dashboard.pdf_theme import PAGE_W, PAGE_H, FONT_REG
from dashboard.pdf_rules import SECCIONES
from dashboard.pdf_pages import PAGINAS

# Re-exportados por compatibilidad con scripts y pruebas anteriores.
from dashboard.pdf_charts import (  # noqa: F401
    _chart_png, _chart_png_fiel, _styled_logo_png, _qr_image, _autodetect_logo,
    _build_simple_price_chart, _build_price_journey_chart, LOGO_PATH,
)


def build_analysis_pdf(analysis) -> bytes:
    """Genera el informe de 7 páginas y devuelve los bytes del PDF."""
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
