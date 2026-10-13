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

SYSCTL_KEY = "net.ipv4.icmp_echo_ignore_broadcasts"


def check_sysctl_value() -> tuple[bool, str]:
    """Memeriksa nilai parameter sysctl net.ipv4.icmp_echo_ignore_broadcasts."""
    try:
        # 1. Cek nilai runtime via sysctl
        res = subprocess.run(
            ["sysctl", "-n", SYSCTL_KEY],
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode != 0:
            return False, f"Parameter sysctl {SYSCTL_KEY} tidak ditemukan pada kernel."

        val = res.stdout.strip()
        if val == "1":
            return True, f"Runtime sysctl {SYSCTL_KEY} sudah bernilai 1 (Compliant)."
        else:
            return False, f"Runtime sysctl {SYSCTL_KEY} bernilai {val} (Seharusnya 1)."
    except Exception as e:
        return False, f"Gagal mengecek sysctl: {str(e)}"


def main():
    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="audit.json",
        catalog="K16",
        cis_id="3.3.4",
        log_type="audit",
    )

    lock_file = acquire_lock("icmp_broadcast_audit", logger)

    try:
        is_compliant, detail = check_sysctl_value()

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
        logger.log_error("K16", "audit", e)

    finally:
        release_lock(lock_file)


if __name__ == "__main__":
    main()