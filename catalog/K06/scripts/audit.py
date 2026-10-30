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
    SSHD_CONFIG, 
    APPROVED_MACS_LIST, 
    CATALOG_LOCKS
)

from pipeline.catalogutils import (
    LogStatus,
    BaseLogger,
    load_taskfile_vars,
    acquire_lock,
    release_lock,
    check_config_exists, 
    check_config_parameter_value,
    get_effective_sshd_parameter 
)


def main():
    task_vars = load_taskfile_vars(SCRIPT_DIR)

    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="audit.json",
        catalog=task_vars.get("ID", "K06"),
        nama=task_vars.get("NAMA", "Pengaturan MACs SSH yang Aman (Integritas Pesan)"),
        kode_cis=task_vars.get("KODE_CIS", "5.1.15"),
        judul_cis=task_vars.get("JUDUL_CIS", "Ensure sshd MACs are configured"),
        versi_cis=task_vars.get("VERSI_CIS", "Ubuntu 24.04 LTS Benchmark v2.0.0"),
        regulasi=task_vars.get("REGULASI", "Pasal 35, Pasal 39"),
        kepatuhan=task_vars.get("KEPATUHAN", "UU PDP No. 27/2022"),
        log_type="audit",
    )
    
    lock_name = CATALOG_LOCKS.get("K06", "sshd_config")
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

        status, _ = check_config_parameter_value(
            SSHD_CONFIG, 
            "MACs"
        )

        if status == "active":
            macs = get_effective_sshd_parameter(
                config_file=SSHD_CONFIG,
                parameter="MACs",
            )

            mac_list = [
                mac.strip()
                for mac in macs.split(",")
                if mac.strip()
            ]

            weak_macs = [x for x in mac_list if x not in APPROVED_MACS_LIST]

            if not weak_macs:
                logger.log(
                    LogStatus.NON_COMPLIANT,
                    "Result",
                    f"Hasil Audit: NON_COMPLIANT - Ditemukan MACs yang tidak disetujui/lemah: {', '.join(weak_macs)}",
                    duration_ms=(perf_counter() - start) * 1000,
                )
                sys.exit(1)
            else:
                logger.log(
                    LogStatus.COMPLIANT,
                    "Result",
                    "Hasil Audit: COMPLIANT - Seluruh MACs yang dikonfigurasi sudah sesuai dengan standar CIS.",
                    duration_ms=(perf_counter() - start) * 1000,
                )
                sys.exit(0)

        elif status == "commented":
            logger.log(
                LogStatus.NON_COMPLIANT, 
                "Result", 
                f"Hasil Audit: NON_COMPLIANT - Parameter 'MACs' pada file {SSHD_CONFIG} dalam posisi dikomentari (belum diatur secara eksplisit).",
                duration_ms=(perf_counter() - start) * 1000,
            )
            sys.exit(1)
        else:
            logger.log(
                LogStatus.FAILED, 
                "Result", 
                f"Hasil Audit: FAILED - Tidak ditemukan parameter 'MACs' pada file {SSHD_CONFIG}.",
                duration_ms=(perf_counter() - start) * 1000,
            )
            sys.exit(1)

    except Exception as e:
        logger.log_error(
            "K06", 
            "audit", 
            e,
            duration_ms=(perf_counter() - start) * 1000,
        )
        sys.exit(2)

    finally:
        release_lock(lock_file)

if __name__ == "__main__":
    main()