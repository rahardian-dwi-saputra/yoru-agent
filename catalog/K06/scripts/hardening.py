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

# Daftar MACs kuat standar CIS 5.1.7
APPROVED_MACS_LIST = [
    "hmac-sha2-512-etm@openssh.com",
    "hmac-sha2-256-etm@openssh.com",
    "umac-128-etm@openssh.com",
    "hmac-sha2-512",
    "hmac-sha2-256",
    "umac-128@openssh.com",
]
HARDENED_MACS_VALUE = ",".join(APPROVED_MACS_LIST)
APPROVED_MACS_SET = set(APPROVED_MACS_LIST)


def parse_macs_from_config(config_path: Path) -> Tuple[str, Optional[List[str]]]:
    """Mengecek dan meng-extract daftar MACs dari file sshd_config."""
    if not config_path.is_file():
        return "not_found", None

    with open(config_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line_stripped = line.strip()

            if line_stripped.startswith("#"):
                uncommented = line_stripped[1:].lstrip()
                if uncommented.lower().startswith("macs"):
                    parts = uncommented.split(maxsplit=1)
                    if len(parts) >= 2:
                        raw_macs = parts[1].strip()
                        return "commented", [m.strip() for m in raw_macs.split(",")]

            elif line_stripped.lower().startswith("macs"):
                parts = line_stripped.split(maxsplit=1)
                if len(parts) >= 2:
                    raw_macs = parts[1].strip()
                    return "active", [m.strip() for m in raw_macs.split(",")]

    return "not_found", None


def apply_hardening_macs(src_path: Path, dst_file_obj, macs_value: str) -> None:
    """Mengubah atau menambahkan baris MACs ke nilai ter-hardening."""
    macs_found = False

    with open(src_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line_stripped = line.strip()

            # Mengubah baris MACs aktif atau terkomentar
            if line_stripped.lower().startswith("macs") or (
                line_stripped.startswith("#")
                and line_stripped[1:].lstrip().lower().startswith("macs")
            ):
                dst_file_obj.write(f"MACs {macs_value}\n")
                macs_found = True
            else:
                dst_file_obj.write(line)

    # Jika direktif MACs tidak pernah ditemukan di file, tambahkan di paling bawah
    if not macs_found:
        dst_file_obj.write(f"\n# Added by CIS Hardening K06\nMACs {macs_value}\n")


def main():
    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="hardening.json",
        catalog="K06",
        cis_id="5.1.7",
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

        # 2. Cek status MACs saat ini
        state, current_macs = parse_macs_from_config(SSHD_CONFIG)

        # Jika sudah aktif dan semua MACs terdaftar di APPROVED_MACS, batalkan
        if state == "active" and current_macs:
            current_set = set(current_macs)
            if (
                current_set.issubset(APPROVED_MACS_SET)
                and current_set == APPROVED_MACS_SET
            ):
                logger.log(
                    "INFO",
                    "Result",
                    "Hasil Hardening: CANCELLED - Parameter MACs sudah ter-hardening dan sesuai standar CIS.",
                )
                sys.exit(0)

        # 3. Buat file konfigurasi sementara dan terapkan hardening
        with tempfile.NamedTemporaryFile(
            "w+", delete=False, prefix="sshd_config_"
        ) as tmp_file:
            tmp_config_path = Path(tmp_file.name)
            apply_hardening_macs(SSHD_CONFIG, tmp_file, HARDENED_MACS_VALUE)

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
                    "Hasil Hardening: SUCCEED - Parameter MACs berhasil diperbarui dan disesuaikan dengan standar CIS.",
                )
            else:
                logger.log(
                    "WARNING",
                    "Result",
                    "Hasil Hardening: WARNING - Konfigurasi MACs berhasil diperbarui, tetapi gagal merestart service SSH.",
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
            f"Terjadi error saat hardening K06: {e}",
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