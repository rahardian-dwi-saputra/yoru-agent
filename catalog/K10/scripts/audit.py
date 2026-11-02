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
    JOURNAL_LOG_DIR,
    CATALOG_LOCKS
)

from pipeline.catalogutils import (
    LogStatus,
    BaseLogger,
    load_taskfile_vars,
    acquire_lock,
    release_lock,
    get_effective_journald_parameter
)


def main():
    task_vars = load_taskfile_vars(SCRIPT_DIR)

    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="audit.json",
        catalog=task_vars.get("ID", "K10"),
        nama=task_vars.get("NAMA", "Penyimpanan Log Journald Permanen"),
        kode_cis=task_vars.get("KODE_CIS", "6.1.2.4"),
        judul_cis=task_vars.get("JUDUL_CIS", "Ensure journald Storage is configured"),
        versi_cis=task_vars.get("VERSI_CIS", "Ubuntu 24.04 LTS Benchmark v2.0.0"),
        regulasi=task_vars.get("REGULASI", "Pasal 31, Pasal 35"),
        kepatuhan=task_vars.get("KEPATUHAN", "UU PDP No. 27/2022"),
        log_type="audit",
    )

    lock_name = CATALOG_LOCKS.get("K10", "journald_audit")
    lock_file = acquire_lock(lock_name, logger)

    start = perf_counter()

    try:
        if not JOURNAL_LOG_DIR.is_dir():
            logger.log(
                LogStatus.FAILED,
                "Result",
                f"Hasil Audit: FAILED - Direktori {JOURNAL_LOG_DIR} tidak ditemukan.",
                duration_ms=(perf_counter() - start) * 1000,
            )
            sys.exit(1)

        storage = get_effective_journald_parameter("Storage").lower()

        if storage != "persistent":
            logger.log(
                LogStatus.NON_COMPLIANT,
                "Result",
                f"Hasil Audit: NON_COMPLIANT - Storage tidak sesuai: ditemukan {storage} diharapkan 'persistent'.",
                duration_ms=(perf_counter() - start) * 1000,
            )
            sys.exit(1)
        else:
            logger.log(
                LogStatus.COMPLIANT,
                "Result",
                f"Hasil Audit: COMPLIANT - Konfigurasi journald Storage=persistent telah sesuai.",
                duration_ms=(perf_counter() - start) * 1000,
            )
            sys.exit(0)

    except Exception as e:
        logger.log_error(
            "K10", 
            "audit", 
            e,
            duration_ms=(perf_counter() - start) * 1000,
        )
        sys.exit(2)
    finally:
        release_lock(lock_file)


if __name__ == "__main__":
    main()