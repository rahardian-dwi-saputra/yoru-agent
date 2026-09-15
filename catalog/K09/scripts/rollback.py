from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Import modul catalogutils via sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]  # Naik 3 level ke yoru-agent/

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.catalogutils import BaseLogger, acquire_lock, release_lock

STATE_FILE = SCRIPT_DIR.parent / "state_k09.txt"


def disable_ufw_service() -> bool:
    """Meng-disable UFW service dan mematikan UFW firewall."""
    try:
        # Disable ufw via command ufw
        res_ufw = subprocess.run(
            ["ufw", "disable"],
            capture_output=True,
            text=True,
        )

        # Disable systemd service
        res_systemd = subprocess.run(
            ["systemctl", "disable", "--now", "ufw"],
            capture_output=True,
            text=True,
        )

        return res_ufw.returncode == 0 and res_systemd.returncode == 0
    except Exception:
        return False


def main():
    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="rollback.json",
        catalog="K09",
        cis_id="4.2.3",
        log_type="rollback",
    )

    lock_file_obj = acquire_lock(logger)

    try:
        # 1. Cek ketersediaan file state_k09.txt
        if not STATE_FILE.is_file():
            logger.log(
                "INFO",
                "Result",
                "Hasil Rollback: CANCELLED - Tidak ada perubahan yang dicatat oleh hardening K09 (state_k09.txt tidak ditemukan).",
            )
            sys.exit(0)

        # 2. Jalankan proses rollback (disable service & ufw)
        if disable_ufw_service():
            if STATE_FILE.exists():
                STATE_FILE.unlink()

            logger.log(
                "SUCCESS",
                "Result",
                "Hasil Rollback: SUCCEED - Layanan 'ufw' berhasil dinonaktifkan (disabled).",
            )
            sys.exit(0)
        else:
            logger.log(
                "FAILED",
                "Result",
                "Hasil Rollback: FAILED - Gagal menonaktifkan layanan 'ufw'.",
            )
            sys.exit(1)

    except Exception as e:
        logger.log(
            "ERROR",
            "Note",
            f"Terjadi error saat rollback K09: {e}",
        )
        logger.log(
            "FAILED",
            "Result",
            "Hasil Rollback: FAILED - Terjadi kesalahan pada proses rollback.",
        )
        sys.exit(1)

    finally:
        release_lock(lock_file_obj)


if __name__ == "__main__":
    main()