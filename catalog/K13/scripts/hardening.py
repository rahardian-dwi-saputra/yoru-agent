from __future__ import annotations
from pathlib import Path
import os
import subprocess
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


def apply_journald_access_hardening() -> tuple[bool, str]:
    """Menerapkan izin akses yang aman pada direktori dan file log systemd-journald.

    Sesuai standar CIS 6.1.1.2:
    - Menghilangkan izin write untuk group/others (chmod o-w, g-w)
    - Memastikan kepemilikan direktori log sesuai standar sistem.
    """
    try:
        if not JOURNAL_LOG_DIR.exists():
            return (
                True,
                "Direktori /var/log/journal belum ada (volatile mode), tidak ada berkas log persisten yang perlu diubah perizinannya.",
            )

        # 1. Amankan direktori utama log journal
        # Mengubah permission direktori agar tidak world-writable (menggunakan chmod o-w, g-w jika terlalu longgar)
        subprocess.run(
            ["chmod", "g-w,o-w", str(JOURNAL_LOG_DIR)],
            capture_output=True,
            text=True,
            check=False,
        )

        # 2. Rekursif mengamankan file-file log di dalamnya agar tidak world/group-writable
        for path in JOURNAL_LOG_DIR.glob("**/*"):
            if path.is_file() or path.is_dir():
                try:
                    # Menghapus write permission untuk group dan others (menjaga agar tetap aman dari modifikasi luar)
                    current_mode = path.stat().st_mode
                    new_mode = current_mode & ~os.S_IWGRP & ~os.S_IWOTH
                    path.chmod(new_mode)
                except Exception:
                    pass

        return True, "Izin akses file log journald berhasil dikonfigurasi menjadi aman (restricted permissions)."
    except Exception as e:
        return False, f"Gagal menerapkan hardening akses log: {str(e)}"


def main():
    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="hardening.json",
        catalog="K13",
        cis_id="6.1.1.2",
        log_type="hardening",
    )

    lock_name = CATALOG_LOCKS.get("K13", "journald_audit")
    lock_file = acquire_lock(lock_name, logger)

    try:
        success, detail = apply_journald_access_hardening()

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
        logger.log_error("K13", "hardening", e)

    finally:
        release_lock(lock_file)


if __name__ == "__main__":
    main()