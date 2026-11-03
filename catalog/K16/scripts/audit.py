from __future__ import annotations
from pathlib import Path
from time import perf_counter
import sys


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]  # Naik 3 level ke yoru-agent/

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import (
    SYSCTL_KEY_ICMP_ECHO_BROADCASTS, 
    SYSCTL_TARGET_ICMP_ECHO_BROADCASTS,
    CATALOG_LOCKS,
)

from pipeline.catalogutils import (
    LogStatus,
    BaseLogger,
    load_taskfile_vars,
    acquire_lock,
    release_lock,
    get_runtime_sysctl_value,
    get_persistent_sysctl_value,
)


def check_sysctl_value() -> tuple[bool, str]:
    """Memeriksa nilai runtime dan konfigurasi persisten sysctl."""

    parameter = SYSCTL_KEY_ICMP_ECHO_BROADCASTS

    runtime_value = get_runtime_sysctl_value(parameter)
    persistent_value = get_persistent_sysctl_value(parameter)

    details = (
        f"Runtime: {runtime_value}, "
        f"Persistent: {persistent_value or 'Tidak ditemukan'}."
    )

    if runtime_value != SYSCTL_TARGET_ICMP_ECHO_BROADCASTS:
        return (
            False,
            f"Runtime {parameter} bernilai {runtime_value}; "
            f"seharusnya {SYSCTL_TARGET_ICMP_ECHO_BROADCASTS}. {details}",
        )

    if persistent_value != SYSCTL_TARGET_ICMP_ECHO_BROADCASTS:
        return (
            False,
            f"Konfigurasi persisten {parameter} belum sesuai. "
            f"Nilai yang diharapkan: {SYSCTL_TARGET_ICMP_ECHO_BROADCASTS}. {details}",
        )

    return (
        True,
        f"Runtime dan konfigurasi persisten {parameter} "
        f"sudah bernilai {SYSCTL_TARGET_ICMP_ECHO_BROADCASTS}. {details}",
    )


def main():
    task_vars = load_taskfile_vars(SCRIPT_DIR)

    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="audit.json",
        catalog=task_vars.get("ID", "K16"),
        nama=task_vars.get("NAMA", "Pengabaian Permintaan ICMP Broadcast"),
        kode_cis=task_vars.get("KODE_CIS", "3.3.4"),
        judul_cis=task_vars.get("JUDUL_CIS", "Ensure broadcast icmp requests are ignored"),
        versi_cis=task_vars.get("VERSI_CIS", "Ubuntu 24.04 LTS Benchmark v2.0.0"),
        regulasi=task_vars.get("REGULASI", "Pasal 35, Pasal 39"),
        kepatuhan=task_vars.get("KEPATUHAN", "UU PDP No. 27/2022"),
        log_type="audit",
    )

    lock_name = CATALOG_LOCKS.get("K16", "icmp_broadcast_audit")
    lock_file = acquire_lock(lock_name, logger)

    start = perf_counter()
    
    try:
        is_compliant, detail = check_sysctl_value()

        if is_compliant:
            logger.log(
                LogStatus.COMPLIANT,
                "Result",
                f"Hasil Audit: COMPLIANT - {detail}",
                duration_ms=(perf_counter() - start) * 1000,
            )
            sys.exit(0)
        else:
            logger.log(
                LogStatus.NON_COMPLIANT,
                "Result",
                f"Hasil Audit: NON_COMPLIANT - {detail}",
                duration_ms=(perf_counter() - start) * 1000,
            )
            sys.exit(1)

    except Exception as e:
        logger.log_error(
            "K16", 
            "audit", 
            e,
            duration_ms=(perf_counter() - start) * 1000,
        )
        sys.exit(2)
    finally:
        release_lock(lock_file)


if __name__ == "__main__":
    main()