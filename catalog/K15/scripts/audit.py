from __future__ import annotations
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import JOURNALD_CONFIG, CATALOG_LOCKS

from pipeline.catalogutils import (
    BaseLogger,
    acquire_lock,
    release_lock,
    check_journald_config_exists,
)


def evaluate_storage_audit(config_path: Path) -> tuple[str, str]:
    """Mengevaluasi apakah Storage=persistent terkonfigurasi dengan benar."""
    if not config_path.is_file():
        return "NON_COMPLIANT", f"Berkas konfigurasi {config_path} tidak ditemukan."

    found_persistent = False
    with open(config_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line_str = line.strip().lower()
            if line_str.startswith("#") or line_str.startswith(";") or "=" not in line_str:
                continue
            key, val = [x.strip() for x in line_str.split("=", 1)]
            if key == "storage" and val == "persistent":
                found_persistent = True
                break

    if found_persistent:
        return "COMPLIANT", "Parameter Storage=persistent sudah sesuai standar CIS."
    return "NON_COMPLIANT", "Parameter Storage belum diatur ke 'persistent'."


def main():
    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="audit.json",
        catalog="K15",
        cis_id="6.1.2.4",
        log_type="audit",
    )

    lock_name = CATALOG_LOCKS.get("K15", "journald_storage")
    lock_file = acquire_lock(lock_name, logger)

    try:
        if not check_journald_config_exists(logger):
            logger.log(
                "NON_COMPLIANT", 
                "Result", 
                f"Hasil Audit: NON_COMPLIANT - Berkas {JOURNALD_CONFIG} tidak ditemukan."
            )
            sys.exit(1)

        status, message = evaluate_storage_audit(JOURNALD_CONFIG)

        if status == "COMPLIANT":
            logger.log(
                "COMPLIANT", 
                "Result", 
                f"Hasil Audit: COMPLIANT - {message}"
            )
        else:
            logger.log(
                "NON_COMPLIANT", 
                "Result", 
                f"Hasil Audit: NON_COMPLIANT - {message}"
            )

    except Exception as e:
        logger.log_error("K15", "audit", e)
       
    finally:
        release_lock(lock_file)


if __name__ == "__main__":
    main()