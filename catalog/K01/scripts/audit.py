from __future__ import annotations
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import SSHD_CONFIG, CATALOG_LOCKS

from pipeline.catalogutils import (
    BaseLogger,
    acquire_lock,
    get_non_root_users,
    check_sshd_config_exists,
    release_lock,
)


def get_permit_root_login_val() -> tuple[str | None, bool]:
    """
    Membaca nilai PermitRootLogin dari sshd_config.
    Mengembalikan tuple: (nilai_string, apakah_ditemukan_secara_aktif)
    Jika dikomentari, mengembalikan (nilai_default_atau_none, False)
    """
    if not SSHD_CONFIG.is_file():
        return None, False

    is_commented = False

    with open(SSHD_CONFIG, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            clean_line = line.strip()
            if not clean_line:
                continue
            
            # Cek apakah baris merupakan komentar yang memuat permitrootlogin
            if clean_line.startswith("#"):
                uncommented = clean_line.lstrip("#").strip()
                parts = uncommented.split()
                if parts and parts[0].lower() == "permitrootlogin" and len(parts) >= 2:
                    is_commented = True
                continue

            # Cek baris aktif (non-komentar)
            parts = clean_line.split()
            if parts and parts[0].lower() == "permitrootlogin" and len(parts) >= 2:
                return parts[1].lower(), True

    # Jika hanya ditemukan dalam bentuk komentar
    if is_commented:
        return "commented", False

    return None, False

def main():
    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="audit.json",
        catalog="K01",
        cis_id="5.1.20",
        log_type="audit",
    )

    lock_name = CATALOG_LOCKS.get("K01", "sshd_config")
    lock_file = acquire_lock(lock_name, logger)

    try:
        if not check_sshd_config_exists(logger):
            logger.log(
                "FAILED", 
                "Result", 
                "Hasil Audit: FAILED - File sshd_config tidak ditemukan."
            )
            sys.exit(1)

        users = get_non_root_users()
        
        if users:
            logger.log(
                "INFO", 
                "Note", 
                f"Ditemukan {len(users)} user non-root aktif: {', '.join(users)}"
            )
        else:
            logger.log(
                "FAILED", 
                "Result", 
                "Hasil Audit: FAILED - Tidak ada user selain root yang ditemukan di sistem."
            )
            sys.exit(1)


        status, is_explicit = get_permit_root_login_val()

        if status is None:
            logger.log(
                "FAILED", 
                "Result", 
                "Hasil Audit: FAILED - Tidak ditemukan parameter PermitRootLogin di sshd_config."
            )
        elif status == "commented":
            logger.log(
                "NON_COMPLIANT", 
                "Result", 
                "Hasil Audit: NON_COMPLIANT - Parameter PermitRootLogin dalam posisi dikomentari (belum diatur secara eksplisit)."
            )
        elif status == "no":
            # Bernilai 'no' (Sesuai CIS)
            logger.log(
                "COMPLIANT", 
                "Result", 
                "Hasil Audit: COMPLIANT - Konfigurasi PermitRootLogin bernilai 'no' sesuai standar CIS."
            )
        elif status == "yes":
            # Bernilai 'yes' (Tidak aman)
            logger.log(
                "NON_COMPLIANT", 
                "Result", 
                "Hasil Audit: NON_COMPLIANT - Konfigurasi PermitRootLogin bernilai 'yes' (Root diizinkan login)."
            )
        else:
            # Nilai lain (seperti prohibit-password, dll., tergantung kebijakan)
            logger.log(
                "NON_COMPLIANT", 
                "Result", 
                f"Hasil Audit: NON_COMPLIANT - Nilai PermitRootLogin '{status}' tidak memenuhi standar mutlak 'no'."
            )

    except Exception as e:
        logger.log_error("K01", "audit", e)
        
    finally:
        release_lock(lock_file)

if __name__ == "__main__":
    main()