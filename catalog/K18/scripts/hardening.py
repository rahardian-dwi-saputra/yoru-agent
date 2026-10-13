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

SYSCTL_CONF = Path("/etc/sysctl.d/60-cis-source-route.conf")
SYSCTL_CONTENT = """# CIS 3.3.8: Ensure source routed packets are not accepted
net.ipv4.conf.all.accept_source_route = 0
net.ipv4.conf.default.accept_source_route = 0
"""


def apply_sysctl_hardening() -> tuple[bool, str]:
    """Menerapkan konfigurasi penolakan source routed packets secara permanen dan runtime."""
    try:
        # 1. Tulis konfigurasi ke file drop-in sysctl.d
        SYSCTL_CONF.parent.mkdir(parents=True, exist_ok=True)
        SYSCTL_CONF.write_text(SYSCTL_CONTENT, encoding="utf-8")

        # 2. Terapkan langsung via sysctl --system
        res = subprocess.run(
            ["sysctl", "--system"],
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode != 0:
            return False, f"Gagal menerapkan sysctl system: {res.stderr.strip()}"

        return True, "Parameter penolakan source routed packets berhasil diterapkan dan disimpan permanen."
    except Exception as e:
        return False, f"Gagal menerapkan hardening sysctl: {str(e)}"


def main():
    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="hardening.json",
        catalog="K18",
        cis_id="3.3.8",
        log_type="hardening",
    )

    lock_file = acquire_lock("source_route_hardening", logger)

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
        logger.log_error("K18", "hardening", e)

    finally:
        release_lock(lock_file)


if __name__ == "__main__":
    main()