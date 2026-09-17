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
    acquire_lock_sshd,
    check_sshd_config_exists,
    release_lock,
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
    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="audit.json",
        catalog="K04",
        cis_id="5.1.16",
        log_type="audit",
    )

    lock_file = acquire_lock_sshd(logger)

    try:
        if not check_sshd_config_exists(logger):
            logger.log(
                "FAILED",
                "Result",
                "Hasil Audit: FAILED - File sshd_config tidak ditemukan.",
            )
            sys.exit(1)

        state, raw_val, tries = get_max_auth_tries_status(SSHD_CONFIG)

        if state == "not_found":
            logger.log(
                "FAILED",
                "Result",
                "Hasil Audit: FAILED - Parameter MaxAuthTries tidak ditemukan di sshd_config (menggunakan default yang tidak aman).",
            )
            sys.exit(1)

        elif state == "commented":
            logger.log(
                "FAILED",
                "Result",
                f"Hasil Audit: FAILED - Parameter MaxAuthTries ditemukan tetapi terkomentar (#) dengan nilai default '{raw_val}'.",
            )
            sys.exit(1)

        elif state == "active":
            if tries is None:
                logger.log(
                    "FAILED",
                    "Result",
                    f"Hasil Audit: FAILED - Parameter MaxAuthTries aktif namun nilainya tidak valid ('{raw_val}').",
                )
                sys.exit(1)

            # Sesuai standar CIS 5.1.16: Harus aktif dan bernilai 1-4 (misal <= 4 dan > 0)
            if 0 < tries <= 4:
                logger.log(
                    "COMPLIANT",
                    "Result",
                    f"Hasil Audit: COMPLIANT - MaxAuthTries dikonfigurasi secara aman dengan nilai {tries} ('{raw_val}').",
                )
            else:
                logger.log(
                    "NON_COMPLIANT",
                    "Result",
                    f"Hasil Audit: NON_COMPLIANT - MaxAuthTries bernilai {tries} ('{raw_val}'). Persyaratan aman: > 0 dan <= 4.",
                )
               
    except Exception as e:
        logger.log_error("K04", "audit", e)

    finally:
        release_lock(lock_file)


if __name__ == "__main__":
    main()