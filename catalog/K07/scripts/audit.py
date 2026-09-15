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

# Daftar KexAlgorithms yang diizinkan sesuai standar CIS 5.1.8
APPROVED_KEX = {
    "curve25519-sha256",
    "curve25519-sha256@libssh.org",
    "diffie-hellman-group14-sha256",
    "diffie-hellman-group16-sha512",
    "diffie-hellman-group18-sha512",
    "ecdh-sha2-nistp256",
    "ecdh-sha2-nistp384",
    "ecdh-sha2-nistp521",
    "sntrup761x25519-sha512@openssh.com",
}


def parse_kex_from_config(config_path: Path) -> Tuple[str, Optional[List[str]]]:
    """Mengecek dan meng-extract daftar KexAlgorithms dari file sshd_config.

    Return:
        Tuple[state, kex_list]
        - state: 'not_found', 'commented', 'active'
        - kex_list: List dari KEX yang ditemukan atau None
    """
    if not config_path.is_file():
        return "not_found", None

    with open(config_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line_stripped = line.strip()

            # 1. Baris Terkomentar (#)
            if line_stripped.startswith("#"):
                uncommented = line_stripped[1:].lstrip()
                if uncommented.lower().startswith("kexalgorithms"):
                    parts = uncommented.split(maxsplit=1)
                    if len(parts) >= 2:
                        raw_kex = parts[1].strip()
                        kex_list = [k.strip() for k in raw_kex.split(",")]
                        return "commented", kex_list

            # 2. Baris Aktif
            elif line_stripped.lower().startswith("kexalgorithms"):
                parts = line_stripped.split(maxsplit=1)
                if len(parts) >= 2:
                    raw_kex = parts[1].strip()
                    kex_list = [k.strip() for k in raw_kex.split(",")]
                    return "active", kex_list

    return "not_found", None


def main():
    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="audit.json",
        catalog="K07",
        cis_id="5.1.8",
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

        # 2. Extract konfigurasi KexAlgorithms
        state, configured_kex = parse_kex_from_config(SSHD_CONFIG)

        # Skenario 1: Parameter KexAlgorithms tidak dikonfigurasi / terkomentar
        if state in ("not_found", "commented"):
            logger.log(
                "NON_COMPLIANT",
                "Result",
                f"Hasil Audit: NON_COMPLIANT - Parameter 'KexAlgorithms' belum dikonfigurasi secara eksplisit (State: {state}).",
            )
            sys.exit(0)

        # Skenario 2: Parameter KexAlgorithms aktif -> Cek apakah ada KEX lemah (misal: SHA1, Group1)
        if state == "active" and configured_kex:
            configured_set = set(configured_kex)
            weak_kex = configured_set - APPROVED_KEX

            if weak_kex:
                logger.log(
                    "NON_COMPLIANT",
                    "Result",
                    f"Hasil Audit: NON_COMPLIANT - Ditemukan KexAlgorithms yang tidak disetujui/lemah: {', '.join(weak_kex)}",
                )
                sys.exit(0)
            else:
                logger.log(
                    "COMPLIANT",
                    "Result",
                    "Hasil Audit: COMPLIANT - Seluruh KexAlgorithms yang dikonfigurasi sudah sesuai dengan standar CIS.",
                )
                sys.exit(0)

    except Exception as e:
        logger.log(
            "ERROR",
            "Note",
            f"Terjadi error saat melakukan audit K07: {e}",
        )
        logger.log(
            "FAILED",
            "Result",
            "Hasil Audit: FAILED - Terjadi kesalahan pada proses audit.",
        )
        sys.exit(1)


if __name__ == "__main__":
    main()