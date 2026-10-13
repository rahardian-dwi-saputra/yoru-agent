from __future__ import annotations
from pathlib import Path
import subprocess
import sys

# Import modul catalogutils via sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]  # Naik 3 level ke yoru-agent/

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.catalogutils import (
    BaseLogger,
    acquire_lock,
    release_lock,
)

SERVICE_NAME = "systemd-journald"


def enable_and_start_journald_service() -> bool:
    """Mengaktifkan (enable) dan menjalankan (start) service systemd-journald."""
    try:
        # Menjalankan systemctl enable --now systemd-journald
        res = subprocess.run(
            ["systemctl", "enable", "--now", SERVICE_NAME],
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
        log_file_name="hardening.json",
        catalog="K13",
        cis_id="6.1.1.1",
        log_type="hardening",
    )

    lock_file = acquire_lock("journald_service_hardening", logger)

    try:
        # Terapkan hardening: pastikan service enabled dan aktif
        success = enable_and_start_journald_service()

        if success:
            logger.log(
                "SUCCESS",
                "Result",
                f"Hasil Hardening: SUCCESS - Service '{SERVICE_NAME}' berhasil diaktifkan dan dijalankan secara otomatis.",
            )
        else:
            logger.log(
                "FAILED",
                "Result",
                f"Hasil Hardening: FAILED - Gagal mengaktifkan atau menjalankan service '{SERVICE_NAME}'.",
            )

    except Exception as e:
        logger.log_error("K13", "hardening", e)

    finally:
        release_lock(lock_file)


if __name__ == "__main__":
    main()