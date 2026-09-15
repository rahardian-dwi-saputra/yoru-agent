from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import List, Optional, Tuple

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
    restart_ssh_service,
)

# Daftar KexAlgorithms kuat standar CIS 5.1.8
APPROVED_KEX_LIST = [
    "curve25519-sha256",
    "curve25519-sha256@libssh.org",
    "diffie-hellman-group14-sha256",
    "diffie-hellman-group16-sha512",
    "diffie-hellman-group18-sha512",
    "ecdh-sha2-nistp256",
    "ecdh-sha2-nistp384",
    "ecdh-sha2-nistp521",
    "sntrup761x25519-sha512@openssh.com",
]
HARDENED_KEX_VALUE = ",".join(APPROVED_KEX_LIST)
APPROVED_KEX_SET = set(APPROVED_KEX_LIST)


def parse_kex_from_config(config_path: Path) -> Tuple[str, Optional[List[str]]]:
    """Mengecek dan meng-extract daftar KexAlgorithms dari file sshd_config."""
    if not config_path.is_file():
        return "not_found", None

    with open(config_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line_stripped = line.strip()

            if line_stripped.startswith("#"):
                uncommented = line_stripped[1:].lstrip()
                if uncommented.lower().startswith("kexalgorithms"):
                    parts = uncommented.split(maxsplit=1)
                    if len(parts) >= 2:
                        raw_kex = parts[1].strip()
                        return "commented", [k.strip() for k in raw_kex.split(",")]

            elif line_stripped.lower().startswith("kexalgorithms"):
                parts = line_stripped.split(maxsplit=1)
                if len(parts) >= 2:
                    raw_kex = parts[1].strip()
                    return "active", [k.strip() for k in raw_kex.split(",")]

    return "not_found", None


def apply_hardening_kex(src_path: Path, dst_file_obj, kex_value: str) -> None:
    """Mengubah atau menambahkan baris KexAlgorithms ke nilai ter-hardening."""
    kex_found = False

    with open(src_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line_stripped = line.strip()

            # Mengubah baris KexAlgorithms aktif atau terkomentar
            if line_stripped.lower().startswith("kexalgorithms") or (
                line_stripped.startswith("#")
                and line_stripped[1:].lstrip().lower().startswith("kexalgorithms")
            ):
                dst_file_obj.write(f"KexAlgorithms {kex_value}\n")
                kex_found = True
            else:
                dst_file_obj.write(line)

    # Jika direktif KexAlgorithms tidak pernah ditemukan di file, tambahkan di paling bawah
    if not kex_found:
        dst_file_obj.write(
            f"\n# Added by CIS Hardening K07\nKexAlgorithms {kex_value}\n"
        )


def main():
    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="hardening.json",
        catalog="K07",
        cis_id="5.1.8",
        log_type="hardening",
    )

    lock_file_obj = acquire_lock(logger)

    try:
        # 1. Cek keberadaan file sshd_config
        if not check_sshd_config_exists(logger):
            logger.log(
                "FAILED",
                "Result",
                "Hasil Hardening: FAILED - File sshd_config tidak ditemukan.",
            )
            sys.exit(1)

        # 2. Cek status KexAlgorithms saat ini
        state, current_kex = parse_kex_from_config(SSHD_CONFIG)

        # Jika sudah aktif dan semua KEX terdaftar di APPROVED_KEX, batalkan
        if state == "active" and current_kex:
            current_set = set(current_kex)
            if (
                current_set.issubset(APPROVED_KEX_SET)
                and current_set == APPROVED_KEX_SET
            ):
                logger.log(
                    "INFO",
                    "Result",
                    "Hasil Hardening: CANCELLED - Parameter KexAlgorithms sudah ter-hardening dan sesuai standar CIS.",
                )
                sys.exit(0)

        # 3. Buat file konfigurasi sementara dan terapkan hardening
        with tempfile.NamedTemporaryFile(
            "w+", delete=False, prefix="sshd_config_"
        ) as tmp_file:
            tmp_config_path = Path(tmp_file.name)
            apply_hardening_kex(SSHD_CONFIG, tmp_file, HARDENED_KEX_VALUE)

        # 4. Validasi sintaks sshd
        validate_cmd = subprocess.run(
            ["sshd", "-t", "-f", str(tmp_config_path)], capture_output=True
        )

        if validate_cmd.returncode == 0:
            shutil.move(str(tmp_config_path), str(SSHD_CONFIG))
            os.chmod(SSHD_CONFIG, 0o600)

            if restart_ssh_service():
                logger.log(
                    "SUCCESS",
                    "Result",
                    "Hasil Hardening: SUCCEED - Parameter KexAlgorithms berhasil diperbarui dan disesuaikan dengan standar CIS.",
                )
            else:
                logger.log(
                    "WARNING",
                    "Result",
                    "Hasil Hardening: WARNING - Konfigurasi KexAlgorithms berhasil diperbarui, tetapi gagal merestart service SSH.",
                )
        else:
            if tmp_config_path.exists():
                tmp_config_path.unlink()
            logger.log(
                "ERROR",
                "Result",
                "Hasil Hardening: CANCELLED - Sintaks konfigurasi invalid! Hardening dibatalkan.",
            )
            sys.exit(1)

    except Exception as e:
        logger.log(
            "ERROR",
            "Note",
            f"Terjadi error saat hardening K07: {e}",
        )
        logger.log(
            "FAILED",
            "Result",
            "Hasil Hardening: FAILED - Terjadi kesalahan pada proses hardening.",
        )
        sys.exit(1)

    finally:
        release_lock(lock_file_obj)


if __name__ == "__main__":
    main()