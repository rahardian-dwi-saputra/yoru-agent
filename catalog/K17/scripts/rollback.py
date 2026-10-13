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

SYSCTL_CONF = Path("/etc/sysctl.d/60-cis-icmp-redirects.conf")


def revert_sysctl_hardening() -> tuple[bool, str]:
    """Menghapus file konfigurasi drop-in dan merefresh ulang konfigurasi kernel."""
    try:
        # 1. Hapus file konfigurasi drop-in jika ada
        if SYSCTL_CONF.exists():
            SYSCTL_CONF.unlink()

        # 2. Reset runtime value kembali ke default (umumnya 1 untuk accept_redirects)
        subprocess.run(
            ["sysctl", "net.ipv4.conf.all.accept_redirects=1"],
            capture_output=True,
            text=True,
            check=False,
        )
        subprocess.run(
            ["sysctl", "net.ipv4.conf.default.accept_redirects=1"],
            capture_output=True,
            text=True,
            check=False,
        )

        # 3. Reload sysctl system
        subprocess.run(
            ["sysctl", "--system"],
            capture_output=True,
            text=True,
            check=False,
        )

        return True, "Konfigurasi ICMP redirects berhasil di-rollback ke kondisi awal."
    except Exception as e:
        return False, f"Gagal melakukan rollback sysctl: {str(e)}"


def main():
    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="rollback.json",
        catalog="K17",
        cis_id="3.3.5",
        log_type="rollback",
    )

    lock_file = acquire_lock("icmp_redirects_rollback", logger)

    try:
        success, detail = revert_sysctl_hardening()

        if success:
            logger.log(
                "SUCCESS",
                "Result",
                f"Hasil Rollback: SUCCESS - {detail}",
            )
        else:
            logger.log(
                "FAILED",
                "Result",
                f"Hasil Rollback: FAILED - {detail}",
            )

    except Exception as e:
        logger.log_error("K17", "rollback", e)

    finally:
        release_lock(lock_file)


if __name__ == "__main__":
    main()