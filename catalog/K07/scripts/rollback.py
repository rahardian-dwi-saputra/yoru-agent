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

# Daftar KexAlgorithms hasil hardening K07
HARDENED_KEX_LIST = [
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
HARDENED_KEX_SET = set(HARDENED_KEX_LIST)


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


def apply_rollback_kex(src_path: Path, dst_file_obj) -> None:
    """Mengomentari atau mengembalikan baris KexAlgorithms ke kondisi default/terkomentar."""
    with open(src_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line_stripped = line.strip()

            # Jika baris merupakan direktif KexAlgorithms aktif, ubah menjadi terkomentar
            if not line_stripped.startswith("#") and line_stripped.lower().startswith(
                "kexalgorithms"
            ):
                dst_file_obj.write(f"# {line_stripped}\n")
            else:
                dst_file_obj.write(line)


def main():
    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="rollback.json",
        catalog="K07",
        cis_id="5.1.8",
        log_type="rollback",
    )

    lock_file = acquire_lock(logger)

    try:
        # 1. Cek keberadaan file sshd_config
        if not check_sshd_config_exists(logger):
            logger.log(
                "FAILED",
                "Result",
                "Hasil Rollback: FAILED - File sshd_config tidak ditemukan.",
            )
            sys.exit(1)

        # 2. Cek status KexAlgorithms saat ini
        state, current_kex = parse_kex_from_config(SSHD_CONFIG)

        # Syarat 1: Parameter tidak ditemukan -> Batalkan rollback
        if state == "not_found":
            logger.log(
                "FAILED",
                "Result",
                "Hasil Rollback: CANCELLED - Parameter KexAlgorithms tidak ditemukan di sshd_config.",
            )
            sys.exit(0)

        # Syarat 2: Parameter terkomentar (#) -> Batalkan rollback
        if state == "commented":
            logger.log(
                "FAILED",
                "Result",
                "Hasil Rollback: CANCELLED - Parameter KexAlgorithms sudah dalam keadaan terkomentar (#).",
            )
            sys.exit(0)

        # Syarat 3: Jika nilainya bukan nilai hasil hardening K07 -> Batalkan rollback
        if state == "active" and current_kex:
            current_set = set(current_kex)
            if current_set != HARDENED_KEX_SET:
                logger.log(
                    "SKIPPED",
                    "Result",
                    "Hasil Rollback: SKIPPED - Konfigurasi KexAlgorithms aktif saat ini bukan berasal dari hasil hardening K07.",
                )
                sys.exit(0)

        # 3. Jalankan proses rollback (mengomentari direktif KexAlgorithms)
        with tempfile.NamedTemporaryFile(
            "w+", delete=False, prefix="sshd_config_"
        ) as tmp_file:
            tmp_config_path = Path(tmp_file.name)
            apply_rollback_kex(SSHD_CONFIG, tmp_file)

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
                    "Hasil Rollback: SUCCEED - Konfigurasi KexAlgorithms berhasil dikembalikan ke kondisi default sistem.",
                )
            else:
                logger.log(
                    "WARNING",
                    "Result",
                    "Hasil Rollback: WARNING - Konfigurasi KexAlgorithms dikembalikan ke default, tetapi gagal merestart service SSH.",
                )
        else:
            if tmp_config_path.exists():
                tmp_config_path.unlink()
            logger.log(
                "FAILED",
                "Result",
                "Hasil Rollback: CANCELLED - Sintaks konfigurasi invalid! Rollback dibatalkan.",
            )
            sys.exit(1)

    except Exception as e:
        logger.log_error("K07", "rollback", e)

    finally:
        release_lock(lock_file)


if __name__ == "__main__":
    main()