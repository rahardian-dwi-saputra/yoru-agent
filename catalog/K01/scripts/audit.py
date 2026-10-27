from __future__ import annotations
from pathlib import Path
from time import perf_counter
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import SSHD_CONFIG, CATALOG_LOCKS

from pipeline.catalogutils import (
    LogStatus,
    BaseLogger,
    acquire_lock,
    release_lock,
    get_non_root_users,
    check_config_exists,
    check_config_parameter_value,
    get_effective_sshd_parameter
)


def main():
    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="audit.json",
        catalog="K01",
        cis_id="5.1.20",
        regulasi="Pasal 35, Pasal 36, Pasal 39",
        kepatuhan="UU PDP No. 27/2022",
        log_type="audit",
    )

    lock_name = CATALOG_LOCKS.get("K01", "sshd_config")
    lock_file = acquire_lock(lock_name, logger)

    start = perf_counter()

    try:
        if not check_config_exists(SSHD_CONFIG, "sshd_config", logger):
            logger.log(
                LogStatus.FAILED,
                "Result", 
                f"Hasil Audit: FAILED - File {SSHD_CONFIG} tidak ditemukan.",
                duration_ms=(perf_counter() - start) * 1000,
            )
            sys.exit(1)

        users = get_non_root_users()
        
        if users:
            logger.log(
                LogStatus.INFO, 
                "Note", 
                f"Ditemukan {len(users)} user non-root aktif: {', '.join(users)}"
            )
        else:
            logger.log(
                LogStatus.FAILED, 
                "Result", 
                "Hasil Audit: FAILED - Tidak ada user selain root yang ditemukan di sistem.",
                duration_ms=(perf_counter() - start) * 1000,
            )
            sys.exit(1)

        status, _ = check_config_parameter_value(
            SSHD_CONFIG, 
            "PermitRootLogin"
        )

        if status == "active":
            value = get_effective_sshd_parameter(
                config_file=SSHD_CONFIG,
                parameter="PermitRootLogin",
            )

            if value == "no":
                logger.log(
                    LogStatus.COMPLIANT, 
                    "Result", 
                    f"Hasil Audit: COMPLIANT - Parameter PermitRootLogin pada file {SSHD_CONFIG} sudah diset ke 'no'",
                    duration_ms=(perf_counter() - start) * 1000,
                )
                sys.exit(0)
            else:
                logger.log(
                    LogStatus.NON_COMPLIANT, 
                    "Result", 
                    f"Hasil Audit: NON_COMPLIANT - Parameter PermitRootLogin pada file {SSHD_CONFIG} bernilai '{value}', seharusnya 'no'.",
                    duration_ms=(perf_counter() - start) * 1000,
                )
                sys.exit(1)

        elif status == "commented":
            logger.log(
                LogStatus.NON_COMPLIANT, 
                "Result", 
                f"Hasil Audit: NON_COMPLIANT - Parameter PermitRootLogin pada file {SSHD_CONFIG} dalam posisi dikomentari (belum diatur secara eksplisit).",
                duration_ms=(perf_counter() - start) * 1000,
            )
            sys.exit(1)
        else:
            logger.log(
                LogStatus.FAILED, 
                "Result", 
                f"Hasil Audit: FAILED - Tidak ditemukan parameter PermitRootLogin pada file {SSHD_CONFIG}.",
                duration_ms=(perf_counter() - start) * 1000,
            )
            sys.exit(1)

    except Exception as e:
        logger.log_error(
            "K01", 
            "audit", 
            e,
            duration_ms=(perf_counter() - start) * 1000,
        )
        sys.exit(2)
        
    finally:
        release_lock(lock_file)

if __name__ == "__main__":
    main()