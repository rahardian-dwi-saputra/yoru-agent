from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# Import modul catalogutils via sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]  # Naik 3 level ke yoru-agent/

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.catalogutils import BaseLogger, acquire_lock, release_lock

STATE_FILE = SCRIPT_DIR.parent / "state_k08.txt"


def is_ufw_installed() -> bool:
    """Memeriksa apakah paket UFW terinstall pada sistem."""
    try:
        res = subprocess.run(
            ["dpkg-query", "-s", "ufw"],
            capture_output=True,
            text=True,
        )
        return res.returncode == 0 and "Status: install ok installed" in res.stdout
    except Exception:
        return False


def purge_ufw() -> bool:
    """Penghapusan/Purge paket UFW menggunakan apt-get."""
    try:
        env = os.environ.copy()
        env["DEBIAN_FRONTEND"] = "noninteractive"
        res = subprocess.run(
            ["apt-get", "purge", "-y", "-q", "ufw"],
            env=env,
            capture_output=True,
            text=True,
        )
        return res.returncode == 0
    except Exception:
        return False


def main():
    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="rollback.json",
        catalog="K08",
        cis_id="4.2.1",
        log_type="rollback",
    )

    lock_file_obj = acquire_lock(logger)

    try:
        # 1. Cek apakah UFW terinstall
        if not is_ufw_installed():
            logger.log(
                "INFO",
                "Result",
                "Hasil Rollback: CANCELLED - Paket 'ufw' tidak terinstall pada sistem.",
            )
            sys.exit(0)

        # 2. Cek apakah UFW diinstall oleh hardening K08 via state file
        if not STATE_FILE.is_file():
            logger.log(
                "INFO",
                "Result",
                "Hasil Rollback: CANCELLED - Paket 'ufw' terinstall di luar manajemen hardening K08 (state_k08.txt tidak ditemukan).",
            )
            sys.exit(0)

        # 3. Eksekusi pencopotan UFW
        if purge_ufw():
            if STATE_FILE.exists():
                STATE_FILE.unlink()

            logger.log(
                "SUCCESS",
                "Result",
                "Hasil Rollback: SUCCEED - Paket 'ufw' berhasil dicopot dari sistem.",
            )
            sys.exit(0)
        else:
            logger.log(
                "FAILED",
                "Result",
                "Hasil Rollback: FAILED - Gagal mencopot paket 'ufw' via apt-get.",
            )
            sys.exit(1)

    except Exception as e:
        logger.log(
            "ERROR",
            "Note",
            f"Terjadi error saat rollback K08: {e}",
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