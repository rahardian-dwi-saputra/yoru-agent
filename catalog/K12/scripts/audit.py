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


def check_journald_service_status() -> tuple[bool, bool, str]:
    """Memeriksa apakah service systemd-journald aktif dan enabled.

    Return:
        tuple[is_active, is_enabled, detail_msg]
    """
    try:
        # Cek apakah service aktif (running)
        active_res = subprocess.run(
            ["systemctl", "is-active", JOURNALD_SERVICE_NAME],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        is_active = active_res.stdout.strip() == "active"

        # Cek apakah service enabled (auto-start saat booting)
        enabled_res = subprocess.run(
            ["systemctl", "is-enabled", JOURNALD_SERVICE_NAME],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        enabled_status = enabled_res.stdout.strip()
        is_enabled = enabled_status in ("enabled", "static", "linked")

        detail = f"Active status: {active_res.stdout.strip()}, Enabled status: {enabled_status}"
        return is_active, is_enabled, detail
    except Exception as e:
        return False, False, str(e)


def main():
    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="audit.json",
        catalog="K12",
        cis_id="6.1.1.1",
        log_type="audit",
    )

    lock_name = CATALOG_LOCKS.get("K12", "journald_audit")
    lock_file = acquire_lock(lock_name, logger)

    try:
        is_active, is_enabled, detail = check_journald_service_status()

        # Skenario: Service tidak aktif atau tidak enabled
        if not is_active or not is_enabled:
            logger.log(
                "NON_COMPLIANT",
                "Result",
                f"Hasil Audit: NON_COMPLIANT - Service systemd-journald tidak memenuhi syarat standar CIS. ({detail})",
            )
        else:
            logger.log(
                "COMPLIANT",
                "Result",
                f"Hasil Audit: COMPLIANT - Service systemd-journald aktif dan terkonfigurasi dengan benar. ({detail})",
            )

    except Exception as e:
        logger.log_error("K12", "audit", e)

    finally:
        release_lock(lock_file)


if __name__ == "__main__":
    main()