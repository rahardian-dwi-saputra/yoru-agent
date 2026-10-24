from __future__ import annotations
from pathlib import Path
import sys


# Import modul catalogutils via sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]  # Naik 3 level ke yoru-agent/

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import (
    UFW_PACKAGE_NAME, 
    UFW_SERVICE_NAME, 
    CATALOG_LOCKS
)

from pipeline.catalogutils import (
    BaseLogger,
    acquire_lock,
    release_lock,
    is_package_installed,
    check_systemd_service_status
)


def main():
    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="audit.json",
        catalog="K12",
        cis_id="4.2.3",
        log_type="audit",
    )

    lock_name = CATALOG_LOCKS.get("K12", "ufw_audit")
    lock_file = acquire_lock(lock_name, logger)

    try:
        if not is_package_installed(UFW_PACKAGE_NAME):
            logger.log(
                "FAILED",
                "Result",
                f"Hasil Audit: FAILED - Paket '{UFW_PACKAGE_NAME}' belum terinstall pada sistem.",
            )
            sys.exit(1)

        is_compliant, runtime_state, startup_state = check_systemd_service_status(UFW_SERVICE_NAME)

        if is_compliant:
            logger.log(
                "COMPLIANT",
                "Result",
                f"Hasil Audit: COMPLIANT - Layanan '{UFW_SERVICE_NAME}' dalam status enabled dan active.",
            )
        else:
            logger.log(
                "NON_COMPLIANT",
                "Result",
                f"Hasil Audit: NON_COMPLIANT - Layanan '{UFW_SERVICE_NAME}' belum aktif/enabled (active={runtime_state}, enabled={startup_state}).",
            )
           
    except Exception as e:
        logger.log_error("K12", "audit", e)

    finally:
        release_lock(lock_file)


if __name__ == "__main__":
    main()