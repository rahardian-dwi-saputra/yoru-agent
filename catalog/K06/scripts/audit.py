from __future__ import annotations

import sys
from pathlib import Path
from typing import List, Optional, Tuple

# Import modul catalogutils via sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]  # Naik 3 level ke yoru-agent/

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.catalogutils import (
    SSHD_CONFIG,
    BaseLogger,
    check_sshd_config_exists,
)

# Daftar MACs yang diizinkan sesuai standar CIS 5.1.7
APPROVED_MACS = {
    "hmac-sha2-512-etm@openssh.com",
    "hmac-sha2-256-etm@openssh.com",
    "umac-128-etm@openssh.com",
    "hmac-sha2-512",
    "hmac-sha2-256",
    "umac-128@openssh.com",
}


def parse_macs_from_config(config_path: Path) -> Tuple[str, Optional[List[str]]]:
    """Mengecek dan meng-extract daftar MACs dari file sshd_config.

    Return:
        Tuple[state, macs_list]
        - state: 'not_found', 'commented', 'active'
        - macs_list: List dari MAC yang ditemukan atau None
    """
    if not config_path.is_file():
        return "not_found", None

    with open(config_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line_stripped = line.strip()

            # 1. Baris Terkomentar (#)
            if line_stripped.startswith("#"):
                uncommented = line_stripped[1:].lstrip()
                if uncommented.lower().startswith("macs"):
                    parts = uncommented.split(maxsplit=1)
                    if len(parts) >= 2:
                        raw_macs = parts[1].strip()
                        macs_list = [m.strip() for m in raw_macs.split(",")]
                        return "commented", macs_list

            # 2. Baris Aktif
            elif line_stripped.lower().startswith("macs"):
                parts = line_stripped.split(maxsplit=1)
                if len(parts) >= 2:
                    raw_macs = parts[1].strip()
                    macs_list = [m.strip() for m in raw_macs.split(",")]
                    return "active", macs_list

    return "not_found", None


def main():
    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="audit.json",
        catalog="K06",
        cis_id="5.1.7",
        log_type="audit",
    )

    try:
        # 1. Cek keberadaan file sshd_config
        if not check_sshd_config_exists(logger):
            logger.log(
                "FAILED",
                "Result",
                "Hasil Audit: FAILED - File sshd_config tidak ditemukan.",
            )
            sys.exit(1)

        # 2. Extract konfigurasi MACs
        state, configured_macs = parse_macs_from_config(SSHD_CONFIG)

        # Skenario 1: Parameter MACs tidak dikonfigurasi / terkomentar
        if state in ("not_found", "commented"):
            logger.log(
                "NON_COMPLIANT",
                "Result",
                f"Hasil Audit: NON_COMPLIANT - Parameter 'MACs' belum dikonfigurasi secara eksplisit (State: {state}).",
            )
            sys.exit(0)

        # Skenario 2: Parameter MACs aktif -> Cek apakah ada MAC lemah (misal: MD5, SHA1)
        if state == "active" and configured_macs:
            configured_set = set(configured_macs)
            weak_macs = configured_set - APPROVED_MACS

            if weak_macs:
                logger.log(
                    "NON_COMPLIANT",
                    "Result",
                    f"Hasil Audit: NON_COMPLIANT - Ditemukan MACs yang tidak disetujui/lemah: {', '.join(weak_macs)}",
                )
                sys.exit(0)
            else:
                logger.log(
                    "COMPLIANT",
                    "Result",
                    "Hasil Audit: COMPLIANT - Seluruh MACs yang dikonfigurasi sudah sesuai dengan standar CIS.",
                )
                sys.exit(0)

    except Exception as e:
        logger.log(
            "ERROR",
            "Note",
            f"Terjadi error saat melakukan audit K06: {e}",
        )
        logger.log(
            "FAILED",
            "Result",
            "Hasil Audit: FAILED - Terjadi kesalahan pada proses audit.",
        )
        sys.exit(1)


if __name__ == "__main__":
    main()