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
    release_lock,
    get_non_root_users,
    check_config_exists,
    check_config_parameter_value
)


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
        if not check_config_exists(SSHD_CONFIG, "sshd_config", logger):
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


        status, value = check_config_parameter_value(SSHD_CONFIG, "PermitRootLogin")

        if status == "active":
            if value and value.lower() == "no":
                logger.log(
                    "COMPLIANT", 
                    "Result", 
                    "Hasil Audit: COMPLIANT - Parameter PermitRootLogin sudah diset ke 'no'"
                )
            else:
                logger.log(
                    "NON_COMPLIANT", 
                    "Result", 
                    f"Hasil Audit: NON_COMPLIANT - Parameter PermitRootLogin bernilai '{value}', seharusnya 'no'."
                )
        elif status == "commented":
            logger.log(
                "NON_COMPLIANT", 
                "Result", 
                "Hasil Audit: NON_COMPLIANT - Parameter PermitRootLogin dalam posisi dikomentari (belum diatur secara eksplisit)."
            )
        else:
            logger.log(
                "FAILED", 
                "Result", 
                "Hasil Audit: FAILED - Tidak ditemukan parameter PermitRootLogin di sshd_config."
            )

    except Exception as e:
        logger.log_error("K01", "audit", e)
        
    finally:
        release_lock(lock_file)

if __name__ == "__main__":
    main()