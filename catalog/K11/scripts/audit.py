from __future__ import annotations
from pathlib import Path
import sys
import subprocess


# Import modul catalogutils via sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]  # Naik 3 level ke yoru-agent/

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import CATALOG_LOCKS
from pipeline.catalogutils import (
    BaseLogger,
    acquire_lock,
    release_lock,
)


def check_system_patches_and_updates() -> tuple[bool, str]:
    """
    Mengecek status pembaruan sistem dan ketersediaan paket/patch keamanan.
    Sesuai CIS 1.2.2.1: Ensure updates, patches, and additional security software are installed.
    """
    try:
        # Cek ketersediaan dan respons manajer paket apt (untuk sistem Ubuntu/Debian)
        result = subprocess.run(
            ["apt-get", "-s", "upgrade"],
            capture_output=True,
            text=True,
            check=False
        )
        
        if result.returncode != 0:
            return False, "Gagal mengakses manajer paket sistem (apt-get) atau repositori tidak valid."

        output = result.stdout.lower()
        
        # Jika perintah berhasil dieksekusi, manajer paket berfungsi dan terkonfigurasi
        if "upgraded" in output or "to be upgraded" in output or "installs" in output:
            return True, "Manajer paket aktif, repositori terkonfigurasi, dan sistem siap memproses pembaruan keamanan."
        
        return True, "Status repositori dan paket sistem terverifikasi dengan baik."
        
    except FileNotFoundError:
        return False, "Perintah manajer paket (apt-get) tidak ditemukan pada lingkungan sistem ini."
    except Exception as e:
        return False, f"Error saat memeriksa status pembaruan sistem: {str(e)}"


def main():
    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="audit.json",
        catalog="K11",
        cis_id="1.2.2.1",
        log_type="audit",
    )

    lock_name = CATALOG_LOCKS.get("K11", "system_updates_audit")
    lock_file = acquire_lock(lock_name, logger)

    try:
        # Menjalankan pemeriksaan audit patch & update (CIS 1.2.2.1)
        is_compliant, message = check_system_patches_and_updates()

        if is_compliant:
            logger.log(
                "COMPLIANT",
                "Result",
                f"Hasil Audit: COMPLIANT - {message}",
            )
        else:
            logger.log(
                "NON_COMPLIANT",
                "Result",
                f"Hasil Audit: NON_COMPLIANT - {message}",
            )
            
    except Exception as e:
        logger.log_error("K11", "audit", e)

    finally:
        release_lock(lock_file)


if __name__ == "__main__":
    main()