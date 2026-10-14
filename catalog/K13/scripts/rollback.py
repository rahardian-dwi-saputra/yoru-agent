from __future__ import annotations
from pathlib import Path
import os
import sys

# Import modul catalogutils via sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]  # Naik 3 level ke yoru-agent/

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import JOURNAL_LOG_DIR, CATALOG_LOCKS

from pipeline.catalogutils import (
    BaseLogger,
    acquire_lock,
    release_lock,
)


def apply_journald_access_rollback() -> tuple[bool, str]:
    """Mengembalikan izin akses direktori dan berkas log systemd-journald 
    ke kondisi standar (mengizinkan grup systemd-journal mengelola file log secara normal).
    """
    try:
        if not JOURNAL_LOG_DIR.exists():
            return (
                True,
                "Direktori /var/log/journal tidak ditemukan, tidak ada berkas log persisten untuk di-rollback.",
            )

        # Mengembalikan izin akses standar direktori utama log journal (misal: 0o2755 atau 0o755 standar systemd)
        # Sesuai paket bawaan systemd, direktori log biasanya 755 atau 2755 dengan kepemilikan root:systemd-journal
        os.chmod(JOURNAL_LOG_DIR, 0o2755)

        # Mengembalikan izin akses file log di dalamnya ke standar aman yang diizinkan systemd (misal: 0o640)
        for path in JOURNAL_LOG_DIR.glob("**/*"):
            if path.is_file():
                try:
                    # Standar file log journald umumnya 0o640 (rw-r-----)
                    path.chmod(0o640)
                except Exception:
                    pass
            elif path.is_dir():
                try:
                    path.chmod(0o755)
                except Exception:
                    pass

        return True, "Izin akses file log journald berhasil dikembalikan ke kondisi standar operasional."
    except Exception as e:
        return False, f"Gagal melakukan rollback akses log: {str(e)}"


def main():
    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="rollback.json",
        catalog="K13",
        cis_id="6.1.1.2",
        log_type="rollback",
    )

    lock_name = CATALOG_LOCKS.get("K13", "journald_audit")
    lock_file = acquire_lock(lock_name, logger)

    try:
        success, detail = apply_journald_access_rollback()

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
        logger.log_error("K13", "rollback", e)

    finally:
        release_lock(lock_file)


if __name__ == "__main__":
    main()