from __future__ import annotations
from pathlib import Path
import subprocess
import sys
import shutil

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


def is_auditd_installed() -> bool:
    """Mengecek apakah paket/binary 'auditd' terinstall pada sistem."""
    if shutil.which("auditd") is not None:
        return True

    try:
        res = subprocess.run(
            ["dpkg-query", "-W", "-f='${Status}'", "auditd"],
            capture_output=True,
            text=True,
        )
        return "install ok installed" in res.stdout
    except Exception:
        return False


def is_auditd_enabled_and_active() -> tuple[bool, bool]:
    """Mengecek apakah auditd service enabled dan active via systemctl.

    Returns:
        tuple[is_enabled, is_active]
    """
    is_enabled = False
    is_active = False

    # 1. Cek systemctl is-enabled auditd
    try:
        res_enabled = subprocess.run(
            ["systemctl", "is-enabled", "auditd"],
            capture_output=True,
            text=True,
        )
        is_enabled = res_enabled.stdout.strip() == "enabled"
    except Exception:
        is_enabled = False

    # 2. Cek systemctl is-active auditd
    try:
        res_active = subprocess.run(
            ["systemctl", "is-active", "auditd"],
            capture_output=True,
            text=True,
        )
        is_active = res_active.stdout.strip() == "active"
    except Exception:
        is_active = False

    return is_enabled, is_active


def main():
    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="audit.json",
        catalog="K08",
        cis_id="4.1.1.2",
        log_type="audit",
    )

    lock_file = acquire_lock("auditid", logger)

    try:
        if not is_auditd_installed():
            logger.log(
                "FAILED",
                "Result",
                "Hasil Audit: FAILED - Paket 'auditd' belum terinstall pada sistem.",
            )
            sys.exit(0)

        # Cek status service auditd
        is_enabled, is_active = is_auditd_enabled_and_active()

        if is_enabled and is_active:
            logger.log(
                "COMPLIANT",
                "Result",
                "Hasil Audit: COMPLIANT - Layanan 'auditd' dalam status enabled dan active.",
            )
            sys.exit(0)
        else:
            status_details = f"enabled={is_enabled}, active={is_active}"
            logger.log(
                "NON_COMPLIANT",
                "Result",
                f"Hasil Audit: NON_COMPLIANT - Layanan 'auditd' belum aktif/enabled ({status_details}).",
            )
            sys.exit(0)

    except Exception as e:
        logger.log_error("K08", "audit", e)

    finally:
        release_lock(lock_file)


if __name__ == "__main__":
    main()