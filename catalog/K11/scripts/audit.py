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
    JOURNALD_ROTATION_BASELINE,
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

def normalize_value(value: str) -> str:
    """Menormalisasi nilai konfigurasi untuk perbandingan."""
    return "".join(value.split()).lower()

def main():
    task_vars = load_taskfile_vars(SCRIPT_DIR)

    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="audit.json",
        catalog=task_vars.get("ID", "K11"),
        nama=task_vars.get("NAMA", "Konfigurasi Rotasi File Log Journald"),
        kode_cis=task_vars.get("KODE_CIS", "6.1.1.3"),
        judul_cis=task_vars.get("JUDUL_CIS", "Ensure journald log file rotation is configured"),
        versi_cis=task_vars.get("VERSI_CIS", "Ubuntu 24.04 LTS Benchmark v2.0.0"),
        regulasi=task_vars.get("REGULASI", "Pasal 31, Pasal 35"),
        kepatuhan=task_vars.get("KEPATUHAN", "UU PDP No. 27/2022"),
        log_type="audit",
    )

    lock_name = CATALOG_LOCKS.get("K11", "journald_audit")
    lock_file = acquire_lock(lock_name, logger)

    start = perf_counter()

    try:
        results: list[str] = []
        compliant = True

        for parameter, expected_value in JOURNALD_ROTATION_BASELINE.items():
            try:
                actual_value = get_effective_journald_parameter(parameter)

                if normalize_value(actual_value) != normalize_value(expected_value):
                    compliant = False
                    results.append(
                        f"{parameter}: tidak sesuai (aktual: {actual_value}, baseline: {expected_value})"
                    )
                else:
                    results.append(
                        f"{parameter}: sesuai ({actual_value})"
                    )
            except RuntimeError as exc:
                compliant = False
                results.append(
                    f"{parameter}: gagal diperiksa ({exc})"
                )


        message = (
            "Konfigurasi Rotasi File Log Journald:\n"
            + "\n".join(f"- {result}" for result in results)
        )

        if compliant:
            logger.log(
                LogStatus.COMPLIANT,
                "Result",
                "Hasil Audit: COMPLIANT - " + message,
                duration_ms=(perf_counter() - start) * 1000,
            )
            sys.exit(0)
        else:
            logger.log(
                LogStatus.NON_COMPLIANT,
                "Result",
                "Hasil Audit: NON_COMPLIANT - " + message,
                duration_ms=(perf_counter() - start) * 1000,
            )
            sys.exit(1)

    except Exception as e:
        logger.log_error(
            "K11", 
            "audit", 
            e,
            duration_ms=(perf_counter() - start) * 1000,
        )
        sys.exit(2)
    finally:
        release_lock(lock_file)


if __name__ == "__main__":
    main()