from __future__ import annotations
from pathlib import Path
from time import perf_counter
import sys

# Import modul catalogutils via sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]  # Naik 3 level ke yoru-agent/

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import JOURNAL_LOG_DIR, CATALOG_LOCKS

from pipeline.catalogutils import (
    LogStatus,
    BaseLogger,
    load_taskfile_vars,
    acquire_lock,
    release_lock,
    check_journald_access
)


def main():
    task_vars = load_taskfile_vars(SCRIPT_DIR)

    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="audit.json",
        catalog=task_vars.get("ID", "K09"),
        nama=task_vars.get("NAMA", "Pengaturan Akses File Log Journald"),
        kode_cis=task_vars.get("KODE_CIS", "6.1.1.2"),
        judul_cis=task_vars.get("JUDUL_CIS", "Ensure journald log file access is configured"),
        versi_cis=task_vars.get("VERSI_CIS", "Ubuntu 24.04 LTS Benchmark v2.0.0"),
        regulasi=task_vars.get("REGULASI", "Pasal 35, Pasal 36"),
        kepatuhan=task_vars.get("KEPATUHAN", "UU PDP No. 27/2022"),
        log_type="audit",
    )

    lock_name = CATALOG_LOCKS.get("K09", "journald_audit")
    lock_file = acquire_lock(lock_name, logger)

    start = perf_counter()

    try:
        is_secure, detail = check_journald_access(JOURNAL_LOG_DIR)

        if not is_secure:

            if "Gagal memeriksa permission log journald" in detail:
                logger.log(
                    LogStatus.FAILED,
                    "Result",
                    f"Hasil Audit: FAILED - {detail}",
                    duration_ms=(perf_counter() - start) * 1000,
                )
                sys.exit(1)
            else:
                logger.log(
                    LogStatus.NON_COMPLIANT,
                    "Result",
                    f"Hasil Audit: NON_COMPLIANT - {detail}",
                    duration_ms=(perf_counter() - start) * 1000,
                )
                sys.exit(1)
        else:
            logger.log(
                LogStatus.COMPLIANT,
                "Result",
                f"Hasil Audit: COMPLIANT - {detail}",
                duration_ms=(perf_counter() - start) * 1000,
            )
            sys.exit(0)

    except Exception as e:
        logger.log_error(
            "K09", 
            "audit", 
            e,
            duration_ms=(perf_counter() - start) * 1000,
        )
        sys.exit(2)
    finally:
        release_lock(lock_file)


if __name__ == "__main__":
    main()