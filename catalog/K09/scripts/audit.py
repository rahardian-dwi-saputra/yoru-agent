from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Import modul catalogutils via sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]  # Naik 3 level ke yoru-agent/

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.catalogutils import BaseLogger


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


def is_ufw_enabled_and_active() -> tuple[bool, bool]:
    """Mengecek apakah ufw service enabled (systemctl) dan aktif (ufw status).

    Returns:
        tuple[is_enabled, is_active]
    """
    is_enabled = False
    is_active = False

    # 1. Cek systemctl is-enabled ufw
    try:
        res_enabled = subprocess.run(
            ["systemctl", "is-enabled", "ufw"],
            capture_output=True,
            text=True,
        )
        is_enabled = res_enabled.stdout.strip() == "enabled"
    except Exception:
        is_enabled = False

    # 2. Cek ufw status
    try:
        res_status = subprocess.run(
            ["ufw", "status"],
            capture_output=True,
            text=True,
        )
        is_active = "Status: active" in res_status.stdout
    except Exception:
        is_active = False

    return is_enabled, is_active


def main():
    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="audit.json",
        catalog="K09",
        cis_id="4.2.3",
        log_type="audit",
    )

    try:
        # 1. Prasyarat: UFW harus terinstall
        if not is_ufw_installed():
            logger.log(
                "NON_COMPLIANT",
                "Result",
                "Hasil Audit: NON_COMPLIANT - Paket 'ufw' belum terinstall pada sistem.",
            )
            sys.exit(0)

        # 2. Cek status service UFW
        is_enabled, is_active = is_ufw_enabled_and_active()

        if is_enabled and is_active:
            logger.log(
                "COMPLIANT",
                "Result",
                "Hasil Audit: COMPLIANT - Layanan 'ufw' dalam status enabled dan active.",
            )
            sys.exit(0)
        else:
            status_details = f"enabled={is_enabled}, active={is_active}"
            logger.log(
                "NON_COMPLIANT",
                "Result",
                f"Hasil Audit: NON_COMPLIANT - Layanan 'ufw' belum aktif/enabled ({status_details}).",
            )
            sys.exit(0)

    except Exception as e:
        logger.log(
            "ERROR",
            "Note",
            f"Terjadi error saat melakukan audit K09: {e}",
        )
        logger.log(
            "FAILED",
            "Result",
            "Hasil Audit: FAILED - Terjadi kesalahan pada proses audit.",
        )
        sys.exit(1)


if __name__ == "__main__":
    main()