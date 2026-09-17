from __future__ import annotations
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.catalogutils import (
    SSHD_CONFIG,
    BaseLogger,
    acquire_lock_sshd,
    get_non_root_users,
    check_sshd_config_exists,
    release_lock,
)

def get_permit_root_login_val() -> str | None:
    """Membaca nilai PermitRootLogin yang aktif (non-commented) dari sshd_config."""
    if not SSHD_CONFIG.is_file():
        return None

    with open(SSHD_CONFIG, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            clean_line = line.strip()
            if clean_line.startswith("#") or not clean_line:
                continue
            
            parts = clean_line.split()
            if parts[0].lower() == "permitrootlogin" and len(parts) >= 2:
                return parts[1].lower()
    return None

def main():
    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="audit.json",
        catalog="K01",
        cis_id="5.1.20",
        log_type="audit",
    )

    lock_file = acquire_lock_sshd(logger)

    try:
        if not check_sshd_config_exists(logger):
            logger.log(
                "FAILED", 
                "Result", 
                "Hasil Audit: FAILED - File sshd_config tidak ditemukan."
            )
            sys.exit(1)

        # Log informasi user non-root (opsional/pendukung)
        users = get_non_root_users()
        if users:
            logger.log(
                "INFO", 
                "Note", 
                f"Ditemukan {len(users)} user non-root aktif: {', '.join(users)}"
            )
        else:
            logger.log(
                "WARNING", 
                "Note", 
                "Tidak ditemukan user non-root aktif."
            )

        # Evaluasi CIS 5.1.20
        status = get_permit_root_login_val()
        
        # Nilai yang tergolong compliant menurut CIS (biasanya 'no', atau 'prohibit-password' jika diizinkan kebijakan)
        is_compliant = status in ["no", "prohibit-password", "without-password"]

        if not status:
            logger.log(
                "WARNING", 
                "Note", 
                "PermitRootLogin tidak diatur secara eksplisit di sshd_config."
            )
        elif not is_compliant:
            logger.log(
                "WARNING", 
                "Note", 
                f"Root BISA login via SSH (PermitRootLogin {status})."
            )
        else:
            logger.log(
                "INFO", 
                "Note", 
                f"Root login SSH dibatasi (PermitRootLogin {status})."
            )

        # Keputusan Akhir Audit
        if is_compliant:
            logger.log(
                "COMPLIANT", 
                "Result", 
                "Hasil Audit: COMPLIANT - Konfigurasi PermitRootLogin sesuai standar CIS."
            )
        else:
            logger.log(
                "NON_COMPLIANT", 
                "Result", 
                "Hasil Audit: NON_COMPLIANT - Konfigurasi PermitRootLogin tidak sesuai standar CIS."
            )

    except Exception as e:
        logger.log_error("K01", "audit", e)
        
    finally:
        release_lock(lock_file)

if __name__ == "__main__":
    main()