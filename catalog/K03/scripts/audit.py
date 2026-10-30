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


def parse_grace_time_to_seconds(raw_value: str) -> Optional[int]:
    """Mengonversi nilai LoginGraceTime (misal: '60', '60s', '1m', '1h') ke satuan detik."""
    val = raw_value.strip().lower()
    try:
        if val.endswith("m"):
            return int(val[:-1]) * 60
        elif val.endswith("h"):
            return int(val[:-1]) * 3600
        elif val.endswith("d"):
            return int(val[:-1]) * 86400
        elif val.endswith("s"):
            return int(val[:-1])
        else:
            return int(val)
    except ValueError:
        return None


def get_login_grace_time_status(
    config_path: Path,
) -> Tuple[str, Optional[str], Optional[int]]:
    """Mengecek status dan nilai LoginGraceTime di sshd_config.

    Return:
        Tuple[state, raw_value, seconds]
        - state: 'not_found', 'commented', 'active'
        - raw_value: Nilai mentah di config (misal '60', '1m')
        - seconds: Nilai dalam detik atau None jika tidak valid
    """
    if not config_path.is_file():
        return "not_found", None, None

    with open(config_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line_stripped = line.strip()

            # 1. Baris Terkomentar
            if line_stripped.startswith("#"):
                uncommented = line_stripped[1:].lstrip()
                if uncommented.lower().startswith("logingracetime"):
                    parts = uncommented.split()
                    raw_val = parts[1] if len(parts) >= 2 else None
                    sec = parse_grace_time_to_seconds(raw_val) if raw_val else None
                    return "commented", raw_val, sec

            # 2. Baris Aktif
            elif line_stripped.lower().startswith("logingracetime"):
                parts = line_stripped.split()
                raw_val = parts[1] if len(parts) >= 2 else None
                sec = parse_grace_time_to_seconds(raw_val) if raw_val else None
                return "active", raw_val, sec

    return "not_found", None, None


def main():
    task_vars = load_taskfile_vars(SCRIPT_DIR)

    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="audit.json",
        catalog=task_vars.get("ID", "K03"),
        nama=task_vars.get("NAMA", "Membatasi Waktu Login SSH (LoginGraceTime)"),
        kode_cis=task_vars.get("KODE_CIS", "5.1.13"),
        judul_cis=task_vars.get("JUDUL_CIS", "Ensure sshd LoginGraceTime is configured"),
        versi_cis=task_vars.get("VERSI_CIS", "Ubuntu 24.04 LTS Benchmark v2.0.0"),
        regulasi=task_vars.get("REGULASI", "Pasal 35, Pasal 39"),
        kepatuhan=task_vars.get("KEPATUHAN", "UU PDP No. 27/2022"),
        log_type="audit",
    )

    lock_name = CATALOG_LOCKS.get("K03", "sshd_config")
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

        state, raw_val, _ = get_login_grace_time_status(SSHD_CONFIG)

        if state == "active":
            login_grace_time = get_effective_sshd_parameter(
                SSHD_CONFIG,
                "LoginGraceTime",
            )

            grace_seconds = parse_grace_time_to_seconds(login_grace_time)

            if grace_seconds is None:
                logger.log(
                    LogStatus.FAILED, 
                    "Result",
                    f"Hasil Audit: FAILED - Parameter LoginGraceTime pada file {SSHD_CONFIG} aktif namun nilainya tidak valid ('{login_grace_time}').",
                    duration_ms=(perf_counter() - start) * 1000,
                )
                sys.exit(1)
            elif 0 < grace_seconds <= 60:
                logger.log(
                    LogStatus.COMPLIANT,
                    "Result",
                    f"Hasil Audit: COMPLIANT - Parameter LoginGraceTime pada file {SSHD_CONFIG} sudah dikonfigurasi secara aman dengan nilai {grace_seconds} detik ('{login_grace_time}').",
                    duration_ms=(perf_counter() - start) * 1000,
                )
                sys.exit(0)
            else:
                logger.log(
                    LogStatus.NON_COMPLIANT,
                    "Result",
                    f"Hasil Audit: NON_COMPLIANT - Parameter LoginGraceTime pada file {SSHD_CONFIG} bernilai {grace_seconds} detik ('{login_grace_time}'). Persyaratan aman: > 0 dan <= 60 detik.",
                    duration_ms=(perf_counter() - start) * 1000,
                )
                sys.exit(1)

        elif state == "commented":
            logger.log(
                LogStatus.FAILED,
                "Result",
                f"Hasil Audit: FAILED - Parameter LoginGraceTime pada file {SSHD_CONFIG} ditemukan tetapi terkomentar (#) dengan nilai default '{raw_val}'.",
                duration_ms=(perf_counter() - start) * 1000,
            )
            sys.exit(1)

        elif state == "not_found":
            logger.log(
                LogStatus.FAILED,
                "Result",
                f"Hasil Audit: FAILED - Parameter LoginGraceTime tidak ditemukan pada file {SSHD_CONFIG} (menggunakan default yang tidak aman).",
                duration_ms=(perf_counter() - start) * 1000,
            )
            sys.exit(1)

    except Exception as e:
        logger.log_error(
            "K03", 
            "audit", 
            e,
            duration_ms=(perf_counter() - start) * 1000,
        )
        sys.exit(2)
    finally:
        release_lock(lock_file)


if __name__ == "__main__":
    main()