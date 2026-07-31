"""
Snapshot del bloque macro — "lo último que se supo", para pintar el inicio al
instante sin esperar a la red.

ADAPTACIÓN respecto al origen (Analista-Mercados): allí estas funciones viven en
data/cache_store.py y escriben también en Upstash. Esta versión NO usa Upstash
(persiste en Supabase + disco), y el plan de migración prohibió traer
cache_store.py. Se conserva el MISMO contrato público (save_macro_snapshot /
get_macro_snapshot, nunca lanzan, guarda solo con datos reales) sobre la caché
de disco local de data/market_data.

Nota deliberada: get_macro_snapshot NO filtra por edad. Su valor es ser "lo
último que se supo", por viejo que sea — quien lo pinta ya lanza el refresco.
"""


def save_macro_snapshot(macro) -> None:
    """Guarda el último registro macro. Nunca lanza.

    Solo guarda si trae rotación sectorial real: así un fallo de red (que
    devuelve el dict a medias o vacío) JAMÁS pisa el último dato bueno."""
    try:
        if not isinstance(macro, dict) or not macro.get("sector_performance"):
            return
        from data.persistence import _make_json_safe
        datos = _make_json_safe(macro)
        try:
            from data.market_data import _save_cache
            _save_cache("macro_snapshot", datos)
        except Exception:
            pass
    except Exception:
        pass


def get_macro_snapshot():
    """Último registro macro conocido, o None. Nunca lanza."""
    try:
        from data.market_data import _load_cache
        # TTL enorme: el snapshot no caduca, solo se sustituye por uno mejor.
        datos = _load_cache("macro_snapshot", ttl_hours=24 * 365)
        if isinstance(datos, dict) and datos.get("sector_performance"):
            return datos
    except Exception:
        pass
    return None
