from __future__ import annotations
from pathlib import Path
import sys
import shutil
import os

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import JOURNALD_CONFIG, JOURNALD_BACKUP_DIR, CATALOG_LOCKS

from pipeline.catalogutils import (
    BaseLogger,
    acquire_lock,
    release_lock,
    check_journald_config_exists,
    restart_journald_service,
)

JOURNALD_PRIMARY_BACKUP = JOURNALD_BACKUP_DIR / "journald.conf.bak"


def main():
    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="rollback.json",
        catalog="K15",
        cis_id="6.1.2.4",
        log_type="rollback",
    )

    lock_name = CATALOG_LOCKS.get("K15", "journald_storage")
    lock_file = acquire_lock(lock_name, logger)

    try:
        if not check_journald_config_exists(logger):
            logger.log(
                "FAILED", 
                "Result", 
                f"Hasil Rollback: FAILED - Berkas target {JOURNALD_CONFIG} tidak ditemukan."
            )
            sys.exit(1)

        if not JOURNALD_PRIMARY_BACKUP.is_file():
            logger.log(
                "FAILED", 
                "Result", 
                f"Hasil Rollback: FAILED - Berkas backup acuan tidak ditemukan di {JOURNALD_PRIMARY_BACKUP}."
            )
            sys.exit(1)

        shutil.copy2(JOURNALD_PRIMARY_BACKUP, JOURNALD_CONFIG)
        os.chmod(JOURNALD_CONFIG, 0o644)

        if restart_journald_service():
            logger.log(
                "SUCCESS", 
                "Result", 
                "Hasil Rollback: SUCCESS - Konfigurasi journald berhasil dipulihkan."
            )
        else:
            logger.log(
                "WARNING", 
                "Result", 
                "Hasil Rollback: WARNING - Konfigurasi disalin tapi gagal restart service."
            )

    except Exception as e:
        logger.log_error("K15", "rollback", e)
        
    finally:
        release_lock(lock_file)


if __name__ == "__main__":
    main()