from __future__ import annotations
from pathlib import Path
from time import perf_counter
import sys


# Import modul catalogutils via sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]  # Naik 3 level ke yoru-agent/

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import (
    AUDITD_PACKAGE_NAME, 
    AUDITD_SERVICE_NAME, 
    CATALOG_LOCKS
)

from pipeline.catalogutils import (
    LogStatus,
    BaseLogger,
    load_taskfile_vars,
    acquire_lock,
    release_lock,
    is_package_installed,
    check_systemd_service_status
)


def main():
    task_vars = load_taskfile_vars(SCRIPT_DIR)

    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="audit.json",
        catalog=task_vars.get("ID", "K08"),
        nama=task_vars.get("NAMA", "Layanan Auditd Aktif dan Berjalan"),
        kode_cis=task_vars.get("KODE_CIS", "6.2.1.2"),
        judul_cis=task_vars.get("JUDUL_CIS", "Ensure auditd service is enabled and active"),
        versi_cis=task_vars.get("VERSI_CIS", "Ubuntu 24.04 LTS Benchmark v2.0.0"),
        regulasi=task_vars.get("REGULASI", "Pasal 35, Pasal 39"),
        kepatuhan=task_vars.get("KEPATUHAN", "UU PDP No. 27/2022"),
        log_type="audit",
    )

    lock_name = CATALOG_LOCKS.get("K08", "auditd")
    lock_file = acquire_lock(lock_name, logger)

    start = perf_counter()

    try:
        if not is_package_installed(AUDITD_PACKAGE_NAME):
            logger.log(
                LogStatus.FAILED,
                "Result",
                f"Hasil Audit: FAILED - Paket '{AUDITD_PACKAGE_NAME}' belum terinstall pada sistem.",
                duration_ms=(perf_counter() - start) * 1000,
            )
            sys.exit(1)

        is_compliant, runtime_state, startup_state = check_systemd_service_status(AUDITD_SERVICE_NAME)
        
        if is_compliant:
            logger.log(
                LogStatus.COMPLIANT,
                "Result",
                f"Hasil Audit: COMPLIANT - Layanan '{AUDITD_SERVICE_NAME}' dalam status enabled dan active.",
                duration_ms=(perf_counter() - start) * 1000,
            )
        else:
            logger.log(
                LogStatus.NON_COMPLIANT,
                "Result",
                f"Hasil Audit: NON_COMPLIANT - Layanan '{AUDITD_SERVICE_NAME}' belum aktif/enabled (active={runtime_state}, enabled={startup_state}).",
                duration_ms=(perf_counter() - start) * 1000,
            )

    except Exception as e:
        logger.log_error(
            "K08", 
            "audit", 
            e,
            duration_ms=(perf_counter() - start) * 1000,
        )

    finally:
        release_lock(lock_file)


if __name__ == "__main__":
    main()