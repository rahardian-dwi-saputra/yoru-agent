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


def check_journald_access() -> tuple[bool, str]:
    """Memeriksa apakah direktori dan berkas log journald memiliki izin akses yang aman.

    Berdasarkan CIS 6.1.1.2: Direktori dan file log tidak boleh memiliki izin
    yang terlalu longgar (world-writable atau group-writable yang tidak sah).
    """
    if not JOURNAL_LOG_DIR.exists():
        return (
            True,
            "Direktori /var/log/journal belum ada (volatile mode aktif), tidak ada file persisten untuk diperiksa.",
        )

    try:
        # Periksa direktori utama /var/log/journal
        st = JOURNAL_LOG_DIR.stat()
        # Cek apakah other memiliki write permission (bit o+w / 0o002)
        if st.st_mode & 0o002:
            return False, f"Direktori {JOURNAL_LOG_DIR} memiliki izin world-writable."

        # Periksa file-file di dalam direktori log
        for path in JOURNAL_LOG_DIR.glob("**/*"):
            if path.is_file():
                p_st = path.stat()
                # Cek apakah group atau other memiliki write permission (g+w atau o+w)
                if p_st.st_mode & 0o022:
                    return False, f"File log ditemukan memiliki izin group/world-writable: {path}"

        return True, "Izin akses direktori dan file log journald sudah aman dan sesuai standar CIS."
    except Exception as e:
        return False, f"Gagal memeriksa izin akses: {str(e)}"


def main():
    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="audit.json",
        catalog="K13",
        cis_id="6.1.1.2",
        log_type="audit",
    )

    lock_name = CATALOG_LOCKS.get("K13", "journald_audit")
    lock_file = acquire_lock(lock_name, logger)

    try:
        is_secure, detail = check_journald_access()

        if not is_secure:
            logger.log(
                "NON_COMPLIANT",
                "Result",
                f"Hasil Audit: NON_COMPLIANT - {detail}",
            )
        else:
            logger.log(
                "COMPLIANT",
                "Result",
                f"Hasil Audit: COMPLIANT - {detail}",
            )

    except Exception as e:
        logger.log_error("K13", "audit", e)

    finally:
        release_lock(lock_file)


if __name__ == "__main__":
    main()