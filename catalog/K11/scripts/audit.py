from __future__ import annotations
from pathlib import Path
import sys

# Import modul catalogutils via sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]  # Naik 3 level ke yoru-agent/

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import JOURNALD_CONFIG, TARGET_SYSTEM_MAX_USE, CATALOG_LOCKS

from pipeline.catalogutils import (
    BaseLogger,
    acquire_lock,
    release_lock,
    check_journald_config_exists,
)


def evaluate_journald_audit(config_path: Path) -> tuple[str, str]:
    """
    Mengevaluasi parameter journald.conf dan mengembalikan status (COMPLIANT/NON_COMPLIANT/WARNING) 
    beserta pesan detailnya.
    """
    if not config_path.is_file():
        return "NON_COMPLIANT", f"Berkas konfigurasi {config_path} tidak ditemukan."

    found_persistent = False
    found_compress = False
    found_max_use = False
    found_retention = False

    with open(config_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line_str = line.strip().lower()
            # Abaikan baris komentar
            if line_str.startswith("#") or line_str.startswith(";") or "=" not in line_str:
                continue

            key, val = [x.strip() for x in line_str.split("=", 1)]
            
            if key == "storage" and val == "persistent":
                found_persistent = True
            elif key == "compress" and val == "yes":
                found_compress = True
            elif key == "systemmaxuse" and val == TARGET_SYSTEM_MAX_USE.lower():
                found_max_use = True
            elif key == "maxretentionsec" in key:  # Fleksibel untuk varian penulisan durasi
                found_retention = True

    # Evaluasi kepatuhan penuh
    if found_persistent and found_compress and found_max_use and found_retention:
        return "COMPLIANT", "Parameter journald (Storage, Compress, SystemMaxUse, MaxRetentionSec) sudah sesuai standar CIS."
    
    # Jika sebagian ada tapi belum lengkap
    missing = []
    if not found_persistent: missing.append("Storage=persistent")
    if not found_compress: missing.append("Compress=yes")
    if not found_max_use: missing.append(f"SystemMaxUse={TARGET_SYSTEM_MAX_USE}")
    if not found_retention: missing.append("MaxRetentionSec")

    return "NON_COMPLIANT", f"Parameter journald belum sepenuhnya ter-hardening. Belum dikonfigurasi / belum sesuai: {', '.join(missing)}"


def main():
    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="audit.json",
        catalog="K14",
        cis_id="6.1.2.3",
        log_type="audit",
    )

    lock_name = CATALOG_LOCKS.get("K14", "journald_audit")
    lock_file = acquire_lock(lock_name, logger)

    try:
        if not check_journald_config_exists(logger):
            logger.log(
                "NON_COMPLIANT",
                "Result",
                f"Hasil Audit: NON_COMPLIANT - Berkas konfigurasi {JOURNALD_CONFIG} tidak ditemukan."
            )
            sys.exit(1)

        status, message = evaluate_journald_audit(JOURNALD_CONFIG)

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
        logger.log_error("K14", "audit", e)

    finally:
        release_lock(lock_file)


if __name__ == "__main__":
    main()