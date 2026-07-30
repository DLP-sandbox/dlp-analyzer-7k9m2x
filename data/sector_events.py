"""
Tipos de evento típicos POR SECTOR — catálogo estático, sin red y sin IA.

Por qué por SECTOR y no por empresa: mantener fechas exactas de cada evento
(WWDC, GTC, CES…) obliga a revisarlas cada año y envejece mal — una fecha
caducada es peor que no tener nada. En su lugar se le dice al modelo QUÉ TIPO de
eventos suele mover a las empresas de ese sector, para que sepa qué buscar en los
hechos materiales y los comunicados que sí llegan con fecha real desde la SEC y
Nasdaq. Cero mantenimiento y nunca caduca.

Mismo contrato que data/industry_labels.py: sin imports, nunca lanza, y devuelve
una lista VACÍA cuando no hay nada que decir — quien lo pinta omite la sección
en vez de mostrar un hueco.
"""

_VACIOS = {"", "unknown", "n/a", "n/d", "none", "-", "—", "nan"}


def _norm(s) -> str:
    try:
        return " ".join(str(s).strip().lower().replace("&", "and").split())
    except Exception:
        return ""


def _es_vacio(s) -> bool:
    return _norm(s) in _VACIOS


# Sector (tal como lo devuelven yfinance/TradingView) → eventos que de verdad
# mueven el precio en ese sector. Redactado en español llano, para que el texto
# del análisis se pueda apoyar en ello sin traducir nada.
_SECTOR_EVENTOS = {
    "technology": [
        "conferencias de producto y keynotes anuales (donde se presentan nuevos aparatos o versiones de software)",
        "lanzamientos de producto y ciclos de renovación",
        "contratos grandes con clientes o proveedores",
        "acuerdos de licencia y disputas de patentes",
    ],
    "communication services": [
        "presentaciones de producto y eventos para desarrolladores",
        "acuerdos de contenido, licencias y derechos de emisión",
        "cambios regulatorios sobre publicidad, datos o competencia",
        "datos de suscriptores y usuarios activos",
    ],
    "healthcare": [
        "aprobaciones y rechazos de la FDA (el regulador de medicamentos en EE. UU.)",
        "resultados de ensayos clínicos por fases",
        "vencimiento de patentes y entrada de genéricos",
        "decisiones de reembolso y precios de medicamentos",
    ],
    "financial services": [
        "decisiones de tipos de interés del banco central",
        "pruebas de resistencia y aprobación de dividendos o recompras",
        "cambios en la morosidad y en las provisiones por impagos",
        "fusiones, adquisiciones y cambios regulatorios",
    ],
    "consumer cyclical": [
        "ventas de la temporada navideña y campañas comerciales clave",
        "lanzamientos de producto y aperturas de tiendas",
        "datos mensuales de ventas comparables",
        "cambios en el coste de materias primas y en el consumo",
    ],
    "consumer defensive": [
        "subidas de precio y su efecto en el volumen vendido",
        "lanzamientos y renovación de marcas",
        "costes de materias primas agrícolas y de envasado",
        "acuerdos con grandes distribuidores",
    ],
    "industrials": [
        "contratos y adjudicaciones grandes (defensa, infraestructura, transporte)",
        "cartera de pedidos y plazos de entrega",
        "planes de inversión pública en infraestructura",
        "ciclos de renovación de maquinaria y flota",
    ],
    "energy": [
        "decisiones de producción de la OPEP y del precio del crudo",
        "descubrimientos, permisos y puesta en marcha de proyectos",
        "cambios regulatorios y ambientales",
        "contratos de suministro a largo plazo",
    ],
    "basic materials": [
        "precio de los metales y materias primas que produce",
        "apertura o parada de minas y plantas",
        "aranceles y restricciones al comercio",
        "contratos de suministro con industria y automoción",
    ],
    "real estate": [
        "decisiones de tipos de interés (afectan de lleno a la financiación)",
        "ocupación, renovación de alquileres y nuevas promociones",
        "compras y ventas de cartera de inmuebles",
        "cambios en la política de dividendos",
    ],
    "utilities": [
        "decisiones del regulador sobre las tarifas que puede cobrar",
        "planes de inversión en red y en renovables",
        "cambios en el precio del combustible que usa para generar",
        "sostenibilidad del dividendo",
    ],
}

# Alias frecuentes de las fuentes → clave canónica
_ALIAS = {
    "information technology": "technology",
    "tech": "technology",
    "communication": "communication services",
    "telecommunications": "communication services",
    "telecom": "communication services",
    "health care": "healthcare",
    "healthcare providers": "healthcare",
    "pharmaceuticals": "healthcare",
    "biotechnology": "healthcare",
    "financials": "financial services",
    "finance": "financial services",
    "banks": "financial services",
    "consumer discretionary": "consumer cyclical",
    "consumer staples": "consumer defensive",
    "materials": "basic materials",
    "industrial": "industrials",
    "oil and gas": "energy",
    "utility": "utilities",
}


def sector_event_types(sector) -> list:
    """Lista de tipos de evento típicos del sector, en español.

    Devuelve [] cuando no hay dato o el sector no está mapeado: quien lo usa
    OMITE el bloque entero en vez de escribir un placeholder. Nunca lanza."""
    try:
        if _es_vacio(sector):
            return []
        key = _norm(sector)
        key = _ALIAS.get(key, key)
        return list(_SECTOR_EVENTOS.get(key, []))
    except Exception:
        return []
