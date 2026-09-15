from __future__ import annotations
from pathlib import Path
from typing import Optional, Tuple
import sys


# Import modul catalogutils via sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]  # Naik 3 level ke yoru-agent/

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.catalogutils import (
    SSHD_CONFIG,
    BaseLogger,
    acquire_lock,
    check_sshd_config_exists,
    release_lock,
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
    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="audit.json",
        catalog="K03",
        cis_id="5.1.13",
        log_type="audit",
    )

    lock_file_obj = acquire_lock(logger)

    logger.log(
        "INFO", 
        "Start", 
        "Memulai audit CIS 5.1.13 (sshd LoginGraceTime)..."
    )

    try:
        if not check_sshd_config_exists(logger):
            logger.log(
                "FAILED", 
                "Result", 
                "Hasil Audit: FAILED - File sshd_config tidak ditemukan."
            )
            sys.exit(1)

        state, raw_val, seconds = get_login_grace_time_status(SSHD_CONFIG)

        if state == "not_found":
            logger.log(
                "FAIL",
                "Result",
                "Hasil Audit: FAILED - Parameter LoginGraceTime tidak ditemukan di sshd_config (menggunakan default yang tidak aman).",
            )
            sys.exit(1)

        elif state == "commented":
            logger.log(
                "FAIL",
                "Result",
                f"Hasil Audit: FAILED - Parameter LoginGraceTime ditemukan tetapi terkomentar (#) dengan nilai default '{raw_val}'.",
            )
            sys.exit(1)

        elif state == "active":
            if seconds is None:
                logger.log(
                    "FAIL",
                    "Result",
                    f"Hasil Audit: FAILED - Parameter LoginGraceTime aktif namun nilainya tidak valid ('{raw_val}').",
                )
                sys.exit(1)

            # Sesuai standar CIS 5.1.13: Harus aktif dan bernilai 1-60 detik (misal <= 60 detik dan > 0)
            if 0 < seconds <= 60:
                logger.log(
                    "PASSED",
                    "Result",
                    f"Hasil Audit: PASSED - LoginGraceTime dikonfigurasi secara aman dengan nilai {seconds} detik ('{raw_val}').",
                )
                sys.exit(0)
            else:
                logger.log(
                    "FAIL",
                    "Result",
                    f"Hasil Audit: FAILED - LoginGraceTime bernilai {seconds} detik ('{raw_val}'). Persyaratan aman: > 0 dan <= 60 detik.",
                )
                sys.exit(1)

    except Exception as e:
        logger.log_error("K03", "audit", e)
        sys.exit(1)

    finally:
        release_lock(lock_file_obj)


if __name__ == "__main__":
    main()