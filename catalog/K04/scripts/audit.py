from __future__ import annotations
from pathlib import Path
from typing import Optional, Tuple
from time import perf_counter
import sys


# Import modul catalogutils via sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]  # Naik 3 level ke yoru-agent/

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import SSHD_CONFIG, CATALOG_LOCKS

from pipeline.catalogutils import (
    LogStatus,
    BaseLogger,
    load_taskfile_vars,
    acquire_lock,
    release_lock,
    check_config_exists,
    get_effective_sshd_parameter
)


def parse_max_auth_tries(raw_value: str) -> Optional[int]:
    """Mengonversi nilai MaxAuthTries ke tipe data integer."""
    try:
        return int(raw_value.strip())
    except ValueError:
        return None


def get_max_auth_tries_status(
    config_path: Path,
) -> Tuple[str, Optional[str], Optional[int]]:
    """Mengecek status dan nilai MaxAuthTries di sshd_config.

    Return:
        Tuple[state, raw_value, tries]
        - state: 'not_found', 'commented', 'active'
        - raw_value: Nilai mentah di config (misal '4')
        - tries: Nilai integer atau None jika tidak valid
    """
    if not config_path.is_file():
        return "not_found", None, None

    with open(config_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line_stripped = line.strip()

            # 1. Baris Terkomentar
            if line_stripped.startswith("#"):
                uncommented = line_stripped[1:].lstrip()
                if uncommented.lower().startswith("maxauthtries"):
                    parts = uncommented.split()
                    raw_val = parts[1] if len(parts) >= 2 else None
                    tries = parse_max_auth_tries(raw_val) if raw_val else None
                    return "commented", raw_val, tries

            # 2. Baris Aktif
            elif line_stripped.lower().startswith("maxauthtries"):
                parts = line_stripped.split()
                raw_val = parts[1] if len(parts) >= 2 else None
                tries = parse_max_auth_tries(raw_val) if raw_val else None
                return "active", raw_val, tries

    return "not_found", None, None


def main():
    task_vars = load_taskfile_vars(SCRIPT_DIR)

    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="audit.json",
        catalog=task_vars.get("ID", "K04"),
        nama=task_vars.get("NAMA", "Membatasi Percobaan Auth SSH (MaxAuthTries)"),
        kode_cis=task_vars.get("KODE_CIS", "5.1.16"),
        judul_cis=task_vars.get("JUDUL_CIS", "Ensure sshd MaxAuthTries is configured"),
        versi_cis=task_vars.get("VERSI_CIS", "Ubuntu 24.04 LTS Benchmark v2.0.0"),
        regulasi=task_vars.get("REGULASI", "Pasal 35, Pasal 39"),
        kepatuhan=task_vars.get("KEPATUHAN", "UU PDP No. 27/2022"),
        log_type="audit",
    )

    lock_name = CATALOG_LOCKS.get("K04", "sshd_config")
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

        state, raw_val, tries = get_max_auth_tries_status(SSHD_CONFIG)

        if state == "active":
            value = get_effective_sshd_parameter(
                config_file=SSHD_CONFIG,
                parameter="MaxAuthTries",
            )

            max_tries = parse_max_auth_tries(value)

            if 1 <= max_tries <= 4:
                logger.log(
                    LogStatus.COMPLIANT, 
                    "Result",
                    f"Hasil Audit: COMPLIANT - Parameter MaxAuthTries pada file {SSHD_CONFIG} sudah dikonfigurasi secara aman dengan nilai {max_tries}.",
                    duration_ms=(perf_counter() - start) * 1000,
                )
                sys.exit(0)
            else:
                logger.log(
                    LogStatus.NON_COMPLIANT, 
                    "Result",
                    f"Hasil Audit: NON_COMPLIANT - Parameter MaxAuthTries pada file {SSHD_CONFIG} bernilai {value}. Persyaratan aman: > 0 dan <= 4.",
                    duration_ms=(perf_counter() - start) * 1000,
                )
                sys.exit(1)

        elif state == "commented":
            logger.log(
                LogStatus.FAILED,
                "Result",
                f"Hasil Audit: FAILED - Parameter MaxAuthTries pada file {SSHD_CONFIG} ditemukan tetapi terkomentar (#) dengan nilai '{raw_val}'.",
                duration_ms=(perf_counter() - start) * 1000,
            )
            sys.exit(1)

        elif state == "not_found":
            logger.log(
                LogStatus.FAILED,
                "Result",
                f"Hasil Audit: FAILED - Parameter MaxAuthTries pada file {SSHD_CONFIG} tidak ditemukan.",
                duration_ms=(perf_counter() - start) * 1000,
            )
            sys.exit(1)

    except Exception as e:
        logger.log_error(
            "K04", 
            "audit", 
            e,
            duration_ms=(perf_counter() - start) * 1000,
        )
        sys.exit(2)
    finally:
        release_lock(lock_file)


if __name__ == "__main__":
    main()