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

SYSCTL_CONF = Path("/etc/sysctl.d/60-cis-tcp-syncookies.conf")
SYSCTL_KEY = "net.ipv4.tcp_syncookies"
TARGET_VALUE = "1"


def apply_sysctl_hardening() -> tuple[bool, str]:
    """Menerapkan konfigurasi sysctl secara permanen dan runtime."""
    try:
        # 1. Tulis konfigurasi ke file drop-in sysctl.d
        conf_content = f"# CIS 3.3.10: Ensure tcp syn cookies is enabled\n{SYSCTL_KEY} = {TARGET_VALUE}\n"
        SYSCTL_CONF.parent.mkdir(parents=True, exist_ok=True)
        SYSCTL_CONF.write_text(conf_content, encoding="utf-8")

        # 2. Terapkan langsung via sysctl --system
        res = subprocess.run(
            ["sysctl", "--system"],
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode != 0:
            return False, f"Gagal menerapkan sysctl system: {res.stderr.strip()}"

        return True, f"Parameter {SYSCTL_KEY} = {TARGET_VALUE} berhasil diterapkan dan disimpan permanen."
    except Exception as e:
        return False, f"Gagal menerapkan hardening sysctl: {str(e)}"


def main():
    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="hardening.json",
        catalog="K19",
        cis_id="3.3.10",
        log_type="hardening",
    )

    lock_file = acquire_lock("tcp_syncookies_hardening", logger)

    try:
        success, detail = apply_sysctl_hardening()

        if success:
            logger.log(
                "SUCCESS",
                "Result",
                f"Hasil Hardening: SUCCESS - {detail}",
            )
        else:
            logger.log(
                "FAILED",
                "Result",
                f"Hasil Hardening: FAILED - {detail}",
            )

    except Exception as e:
        logger.log_error("K19", "hardening", e)

    finally:
        release_lock(lock_file)


if __name__ == "__main__":
    main()