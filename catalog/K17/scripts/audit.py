from __future__ import annotations
from pathlib import Path
import subprocess
import sys

# Import modul catalogutils via sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]  # Naik 3 level ke yoru-agent/

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import SYSCTL_KEYS_ACCEPT_REDIRECTS, CATALOG_LOCKS

from pipeline.catalogutils import (
    BaseLogger,
    acquire_lock,
    release_lock,
)


def check_sysctl_values() -> tuple[bool, str]:
    """Memeriksa nilai parameter sysctl untuk penolakan ICMP redirects."""
    try:
        failed_keys = []
        details = []

        for key in SYSCTL_KEYS_ACCEPT_REDIRECTS:
            res = subprocess.run(
                ["sysctl", "-n", key],
                capture_output=True,
                text=True,
                check=False,
            )
            if res.returncode != 0:
                failed_keys.append(key)
                continue

            val = res.stdout.strip()
            if val != "0":
                failed_keys.append(key)
                details.append(f"{key}={val} (seharusnya 0)")
            else:
                details.append(f"{key}=0 (OK)")

        if failed_keys:
            return False, f"Parameter belum sesuai standar CIS: {', '.join(details)}"
        
        return True, f"Semua parameter ICMP redirects sudah aman: {', '.join(details)}"
    except Exception as e:
        return False, f"Gagal mengecek sysctl: {str(e)}"


def main():
    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="audit.json",
        catalog="K17",
        cis_id="3.3.5",
        log_type="audit",
    )

    lock_name = CATALOG_LOCKS.get("K17", "icmp_redirects_audit")
    lock_file = acquire_lock(lock_name, logger)

    try:
        is_compliant, detail = check_sysctl_values()

        if is_compliant:
            logger.log(
                "COMPLIANT",
                "Result",
                f"Hasil Audit: COMPLIANT - {detail}",
            )
        else:
            logger.log(
                "NON_COMPLIANT",
                "Result",
                f"Hasil Audit: NON_COMPLIANT - {detail}",
            )

    except Exception as e:
        logger.log_error("K17", "audit", e)

    finally:
        release_lock(lock_file)


if __name__ == "__main__":
    main()