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


def install_ufw() -> bool:
    """Meng-install UFW menggunakan apt-get."""
    try:
        env = os.environ.copy()
        env["DEBIAN_FRONTEND"] = "noninteractive"
        res = subprocess.run(
            ["apt-get", "update", "-q"],
            env=env,
            capture_output=True,
            text=True,
        )
        install_res = subprocess.run(
            ["apt-get", "install", "-y", "-q", "ufw"],
            env=env,
            capture_output=True,
            text=True,
        )
        return install_res.returncode == 0
    except Exception:
        return False


def main():
    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="hardening.json",
        catalog="K08",
        cis_id="4.2.1",
        log_type="hardening",
    )

    lock_file_obj = acquire_lock(logger)

    try:
        # 1. Cek apakah UFW sudah terinstall
        if is_ufw_installed():
            logger.log(
                "INFO",
                "Result",
                "Hasil Hardening: CANCELLED - Paket 'ufw' sudah terinstall sebelumnya.",
            )
            sys.exit(0)

        # 2. Install UFW
        if install_ufw():
            # Catat state bahwa UFW diinstall oleh script hardening ini (untuk keperluan rollback)
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                f.write("installed_by_k08=true\n")

            logger.log(
                "SUCCESS",
                "Result",
                "Hasil Hardening: SUCCEED - Paket 'ufw' berhasil diinstall pada sistem.",
            )
            sys.exit(0)
        else:
            logger.log(
                "FAILED",
                "Result",
                "Hasil Hardening: FAILED - Gagal menginstall paket 'ufw' via apt-get.",
            )
            sys.exit(1)

    except Exception as e:
        logger.log(
            "ERROR",
            "Note",
            f"Terjadi error saat hardening K08: {e}",
        )
        logger.log(
            "FAILED",
            "Result",
            "Hasil Hardening: FAILED - Terjadi kesalahan pada proses hardening.",
        )
        sys.exit(1)

    finally:
        release_lock(lock_file_obj)


if __name__ == "__main__":
    main()