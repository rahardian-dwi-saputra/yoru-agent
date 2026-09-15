from __future__ import annotations
from pathlib import Path
from typing import List, Optional, Tuple
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

# Daftar Ciphers yang diizinkan sesuai standar CIS 5.1.6
APPROVED_CIPHERS = {
    "chacha20-poly1305@openssh.com",
    "aes256-gcm@openssh.com",
    "aes128-gcm@openssh.com",
    "aes256-ctr",
    "aes192-ctr",
    "aes128-ctr",
}


def parse_ciphers_from_config(config_path: Path) -> Tuple[str, Optional[List[str]]]:
    """
    Mengecek dan meng-extract daftar Ciphers dari file sshd_config.
    
    Return:
        Tuple[state, ciphers_list]
        - state: 'not_found', 'commented', 'active'
        - ciphers_list: List dari cipher yang ditemukan atau None
    """
    if not config_path.is_file():
        return "not_found", None

    with open(config_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line_stripped = line.strip()

            # 1. Baris Terkomentar (#)
            if line_stripped.startswith("#"):
                uncommented = line_stripped[1:].lstrip()
                if uncommented.lower().startswith("ciphers"):
                    parts = uncommented.split(maxsplit=1)
                    if len(parts) >= 2:
                        raw_ciphers = parts[1].strip()
                        ciphers_list = [c.strip() for c in raw_ciphers.split(",")]
                        return "commented", ciphers_list

            # 2. Baris Aktif
            elif line_stripped.lower().startswith("ciphers"):
                parts = line_stripped.split(maxsplit=1)
                if len(parts) >= 2:
                    raw_ciphers = parts[1].strip()
                    ciphers_list = [c.strip() for c in raw_ciphers.split(",")]
                    return "active", ciphers_list

    return "not_found", None


def main():
    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="audit.json",
        catalog="K05",
        cis_id="5.1.6",
        log_type="audit",
    )

    lock_file_obj = acquire_lock(logger)
    
    logger.log(
        "INFO",
        "Start",
        "Memulai audit CIS 5.1.6 (sshd Ciphers)...",
    )

    try:
        if not check_sshd_config_exists(logger):
            logger.log(
                "FAILED",
                "Result",
                "Hasil Audit: FAILED - File sshd_config tidak ditemukan.",
            )
            sys.exit(1)

        state, configured_ciphers = parse_ciphers_from_config(SSHD_CONFIG)

        # Skenario 1: Parameter Ciphers tidak dikonfigurasi / terkomentar
        if state in ("not_found", "commented"):
            logger.log(
                "FAIL",
                "Result",
                f"Hasil Audit: FAILED - Parameter 'Ciphers' belum dikonfigurasi secara eksplisit (State: {state}).",
            )
            sys.exit(0)

        # Skenario 2: Parameter Ciphers aktif -> Cek apakah ada cipher lemah
        if state == "active" and configured_ciphers:
            configured_set = set(configured_ciphers)
            weak_ciphers = configured_set - APPROVED_CIPHERS

            if weak_ciphers:
                logger.log(
                    "FAIL",
                    "Result",
                    f"Hasil Audit: FAILED - Ditemukan Ciphers yang tidak disetujui/lemah: {', '.join(weak_ciphers)}",
                )
                sys.exit(0)
            else:
                logger.log(
                    "PASSED",
                    "Result",
                    "Hasil Audit: PASSED - Seluruh Ciphers yang dikonfigurasi sudah sesuai dengan standar CIS.",
                )
                sys.exit(0)

    except Exception as e:
        logger.log_error("K05", "audit", e)
        sys.exit(1)

    finally:
        release_lock(lock_file_obj)


if __name__ == "__main__":
    main()