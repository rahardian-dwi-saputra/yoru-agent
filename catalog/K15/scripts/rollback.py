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

JOURNALD_CONFIG = Path("/etc/systemd/journald.conf")


def revert_journald_compress(config_path: Path) -> bool:
    """Mengembalikan konfigurasi Compress (misalnya diubah menjadi no atau dikomentari)."""
    if not config_path.is_file():
        return False

    lines = []
    with open(config_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line_stripped = line.strip()
            # Ubah Compress=yes menjadi Compress=no atau komentari
            if line_stripped.lower().startswith("compress="):
                lines.append("#Compress=no\n")
            else:
                lines.append(line)

    with open(config_path, "w", encoding="utf-8") as f:
        f.writelines(lines)

    return True


def restart_journald_service() -> bool:
    try:
        res = subprocess.run(
            ["systemctl", "restart", "systemd-journald"],
            capture_output=True,
            text=True,
            check=False,
        )
        return res.returncode == 0
    except Exception:
        return False


def main():
    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="rollback.json",
        catalog="K15",
        cis_id="6.1.2.3",
        log_type="rollback",
    )

    lock_file = acquire_lock("journald_compress_rollback", logger)

    try:
        if not JOURNALD_CONFIG.is_file():
            logger.log(
                "FAILED",
                "Result",
                f"Hasil Rollback: FAILED - Berkas konfigurasi {JOURNALD_CONFIG} tidak ditemukan.",
            )
            return

        success = revert_journald_compress(JOURNALD_CONFIG)

        if not success:
            logger.log(
                "FAILED",
                "Result",
                "Hasil Rollback: FAILED - Gagal mengubah konfigurasi journald.",
            )
            return

        if restart_journald_service():
            logger.log(
                "SUCCESS",
                "Result",
                "Hasil Rollback: SUCCESS - Konfigurasi 'Compress' berhasil di-rollback dan service journald di-restart.",
            )
        else:
            logger.log(
                "FAILED",
                "Result",
                "Hasil Rollback: FAILED - Konfigurasi diubah tetapi gagal merestart service systemd-journald.",
            )

    except Exception as e:
        logger.log_error("K15", "rollback", e)

    finally:
        release_lock(lock_file)


if __name__ == "__main__":
    main()