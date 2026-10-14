from __future__ import annotations
from pathlib import Path
import subprocess
import sys

# Import modul catalogutils via sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]  # Naik 3 level ke yoru-agent/

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import JOURNALD_SERVICE_NAME, CATALOG_LOCKS

from pipeline.catalogutils import (
    BaseLogger,
    acquire_lock,
    release_lock,
)


def disable_journald_service() -> bool:
    """
    Mengembalikan konfigurasi dengan menonaktifkan (disable) service systemd-journald.
    Catatan: Secara CIS benchmark hal ini tidak direkomendasikan, namun disediakan 
    sebagai fungsi pembalik (rollback) jika diperlukan oleh preferensi sistem.
    """
    try:
        # Menjalankan systemctl disable systemd-journald
        res = subprocess.run(
            ["systemctl", "disable", JOURNALD_SERVICE_NAME],
            capture_output=True,
            text=True,
            check=False,
        )
        return res.returncode == 0
    except Exception:
        return False


def main():
    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="rollback.json",
        catalog="K12",
        cis_id="6.1.1.1",
        log_type="rollback",
    )

    lock_name = CATALOG_LOCKS.get("K12", "journald_audit")
    lock_file = acquire_lock(lock_name, logger)

    try:
        # Terapkan rollback (menonaktifkan autostart service jika dikembalikan ke awal)
        success = disable_journald_service()

        if success:
            logger.log(
                "SUCCESS",
                "Result",
                f"Hasil Rollback: SUCCESS - Status auto-start (enabled) untuk service '{JOURNALD_SERVICE_NAME}' berhasil dibatalkan/di-disable.",
            )
        else:
            logger.log(
                "FAILED",
                "Result",
                f"Hasil Rollback: FAILED - Gagal mengubah status service '{JOURNALD_SERVICE_NAME}'.",
            )

    except Exception as e:
        logger.log_error("K12", "rollback", e)

    finally:
        release_lock(lock_file)


if __name__ == "__main__":
    main()