"""
Migración one-shot: sube los análisis y scans del filesystem local
(.history/) a Supabase. Solo hace falta correrlo UNA vez después de
configurar SUPABASE_URL + SUPABASE_SERVICE_KEY en el .env.

Uso:
    python3 scripts/migrate_to_supabase.py
"""
import json
import sys
from datetime import datetime
from pathlib import Path

# Hacer importable el módulo data.persistence
sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv(str(Path(__file__).parent.parent / ".env"))

from data.persistence import (
    _supabase_client, _make_json_safe, OWNER_UID,
    HISTORY_DIR, ANALYSES_DIR, SCANS_DIR,
)


def migrate_analyses(sb) -> tuple[int, int]:
    """Sube todos los .history/analyses/*.json a la tabla user_analyses."""
    if not ANALYSES_DIR.exists():
        print("  (no hay carpeta .history/analyses/)")
        return 0, 0
    files = sorted(ANALYSES_DIR.glob("*.json"))
    print(f"\n[ANÁLISIS] Encontré {len(files)} archivos locales")
    ok = 0
    fail = 0
    for path in files:
        try:
            data = json.loads(path.read_text())
            ticker = data.get("ticker", path.stem)
            safe = _make_json_safe(data)
            sb.table("user_analyses").upsert({
                "uid":        OWNER_UID,
                "ticker":     ticker,
                "data":       safe,
                "updated_at": datetime.now().isoformat(),
            }).execute()
            print(f"  ✓ {ticker}")
            ok += 1
        except Exception as e:
            print(f"  ✗ {path.name}: {e}")
            fail += 1
    return ok, fail


def migrate_scans(sb) -> tuple[int, int]:
    """Sube todos los .history/scans/scan_*.json a la tabla user_scans."""
    if not SCANS_DIR.exists():
        print("  (no hay carpeta .history/scans/)")
        return 0, 0
    files = sorted(SCANS_DIR.glob("scan_*.json"))
    print(f"\n[SCANS] Encontré {len(files)} archivos locales")
    ok = 0
    fail = 0
    for path in files:
        try:
            data = json.loads(path.read_text())
            scan_id = data.get("scan_id") or path.stem.replace("scan_", "")
            safe = _make_json_safe(data)
            sb.table("user_scans").upsert({
                "uid":     OWNER_UID,
                "scan_id": scan_id,
                "label":   data.get("label", ""),
                "count":   data.get("count", 0),
                "data":    safe,
            }).execute()
            print(f"  ✓ {scan_id} ({data.get('count', 0)} candidatos)")
            ok += 1
        except Exception as e:
            print(f"  ✗ {path.name}: {e}")
            fail += 1
    return ok, fail


def main():
    print("═══ Migración local → Supabase ═══")
    sb = _supabase_client()
    if sb is None:
        print("\n❌ ERROR: Supabase no está configurado.")
        print("   Verificá que SUPABASE_URL y SUPABASE_SERVICE_KEY estén en .env")
        sys.exit(1)
    print("✓ Conexión a Supabase OK")

    an_ok, an_fail = migrate_analyses(sb)
    sc_ok, sc_fail = migrate_scans(sb)

    print(f"\n═══ Resumen ═══")
    print(f"Análisis subidos:  {an_ok} OK · {an_fail} fallos")
    print(f"Scans subidos:     {sc_ok} OK · {sc_fail} fallos")
    print("\n✓ Migración completa. Tus análisis ya viven en la cloud.")


if __name__ == "__main__":
    main()
