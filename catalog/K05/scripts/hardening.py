from __future__ import annotations
from pathlib import Path
from typing import List, Optional, Tuple
import os
import shutil
import subprocess
import sys
import tempfile


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

# Daftar Ciphers kuat standar CIS 5.1.6
APPROVED_CIPHERS_LIST = [
    "chacha20-poly1305@openssh.com",
    "aes256-gcm@openssh.com",
    "aes128-gcm@openssh.com",
    "aes256-ctr",
    "aes192-ctr",
    "aes128-ctr",
]
HARDENED_CIPHERS_VALUE = ",".join(APPROVED_CIPHERS_LIST)
APPROVED_CIPHERS_SET = set(APPROVED_CIPHERS_LIST)


def parse_ciphers_from_config(config_path: Path) -> Tuple[str, Optional[List[str]]]:
    """Mengecek dan meng-extract daftar Ciphers dari file sshd_config."""
    if not config_path.is_file():
        return "not_found", None

    with open(config_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line_stripped = line.strip()

            if line_stripped.startswith("#"):
                uncommented = line_stripped[1:].lstrip()
                if uncommented.lower().startswith("ciphers"):
                    parts = uncommented.split(maxsplit=1)
                    if len(parts) >= 2:
                        raw_ciphers = parts[1].strip()
                        return "commented", [c.strip() for c in raw_ciphers.split(",")]

            elif line_stripped.lower().startswith("ciphers"):
                parts = line_stripped.split(maxsplit=1)
                if len(parts) >= 2:
                    raw_ciphers = parts[1].strip()
                    return "active", [c.strip() for c in raw_ciphers.split(",")]

    return "not_found", None


def apply_hardening_ciphers(
    src_path: Path, dst_file_obj, ciphers_value: str
) -> None:
    """Mengubah atau menambahkan baris Ciphers ke nilai ter-hardening."""
    ciphers_found = False

    with open(src_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line_stripped = line.strip()

            # Mengubah baris Ciphers aktif atau terkomentar
            if line_stripped.lower().startswith("ciphers") or (
                line_stripped.startswith("#")
                and line_stripped[1:].lstrip().lower().startswith("ciphers")
            ):
                dst_file_obj.write(f"Ciphers {ciphers_value}\n")
                ciphers_found = True
            else:
                dst_file_obj.write(line)

    # Jika direktif Ciphers tidak pernah ditemukan di file, tambahkan di paling bawah
    if not ciphers_found:
        dst_file_obj.write(f"\n# Added by CIS Hardening K05\nCiphers {ciphers_value}\n")


def main():
    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="hardening.json",
        catalog="K05",
        cis_id="5.1.6",
        log_type="hardening",
    )

    lock_file_obj = acquire_lock(logger)

    try:
        if not check_sshd_config_exists(logger):
            logger.log(
                "FAILED",
                "Result",
                "Hasil Hardening: FAILED - File sshd_config tidak ditemukan.",
            )
            sys.exit(1)

        # 2. Cek status Ciphers saat ini
        state, current_ciphers = parse_ciphers_from_config(SSHD_CONFIG)

        # Jika sudah aktif dan semua ciphers terdaftar di APPROVED_CIPHERS, batalkan
        if state == "active" and current_ciphers:
            current_set = set(current_ciphers)
            if current_set.issubset(APPROVED_CIPHERS_SET) and current_set == APPROVED_CIPHERS_SET:
                logger.log(
                    "INFO",
                    "Result",
                    "Hasil Hardening: CANCELLED - Parameter Ciphers sudah ter-hardening dan sesuai standar CIS.",
                )
                sys.exit(0)

        # 3. Buat file konfigurasi sementara dan terapkan hardening
        with tempfile.NamedTemporaryFile(
            "w+", delete=False, prefix="sshd_config_"
        ) as tmp_file:
            tmp_config_path = Path(tmp_file.name)
            apply_hardening_ciphers(SSHD_CONFIG, tmp_file, HARDENED_CIPHERS_VALUE)

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
                    "Hasil Hardening: SUCCEED - Parameter Ciphers berhasil diperbarui dan disesuaikan dengan standar CIS.",
                )
            else:
                logger.log(
                    "WARNING",
                    "Result",
                    "Hasil Hardening: WARNING - Konfigurasi Ciphers berhasil diperbarui, tetapi gagal merestart service SSH.",
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
        logger.log_error("K05", "hardening", e)
        sys.exit(1)

    finally:
        release_lock(lock_file_obj)


if __name__ == "__main__":
    main()