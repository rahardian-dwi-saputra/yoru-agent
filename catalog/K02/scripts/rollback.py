from __future__ import annotations
from pathlib import Path
from typing import Optional, Tuple
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


def check_password_auth_state(
    config_path: Path,
) -> Tuple[str, Optional[str]]:
    """Mengecek keberadaan dan nilai PasswordAuthentication di sshd_config.

    Return:
        Tuple[state, value]
        - state: 'not_found', 'commented', 'active'
        - value: Nilai parameter (misal 'yes', 'no') atau None jika tidak ada
    """
    if not config_path.is_file():
        return "not_found", None

    with open(config_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line_stripped = line.strip()

            # 1. Baris Terkomentar
            if line_stripped.startswith("#"):
                uncommented = line_stripped[1:].lstrip()
                if uncommented.lower().startswith("passwordauthentication"):
                    parts = uncommented.split()
                    val = parts[1] if len(parts) >= 2 else None
                    return "commented", val

            # 2. Baris Aktif
            elif line_stripped.lower().startswith("passwordauthentication"):
                parts = line_stripped.split()
                val = parts[1] if len(parts) >= 2 else None
                return "active", val

    return "not_found", None


def apply_rollback_logic(src_path: Path, dst_file_obj) -> None:
    """Mengubah parameter PasswordAuthentication aktif yang bernilai 'no' menjadi 'yes'."""
    with open(src_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line_stripped = line.strip()

            if not line_stripped.startswith(
                "#"
            ) and line_stripped.lower().startswith("passwordauthentication"):
                dst_file_obj.write("PasswordAuthentication yes\n")
            else:
                dst_file_obj.write(line)


def main():
    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="rollback.json",
        catalog="K02",
        cis_id="5.2.14",
        log_type="rollback",
    )

    lock_file_obj = acquire_lock(logger)

    try:
        if not check_sshd_config_exists(logger):
            logger.log(
                "FAILED", 
                "Result", 
                "Hasil Rollback: FAILED - File sshd_config tidak ditemukan."
            )
            sys.exit(1)

        # Cek status parameter PasswordAuthentication di sshd_config
        state, value = check_password_auth_state(SSHD_CONFIG)

        # 1. Jika parameter tidak ditemukan -> Batalkan rollback
        if state == "not_found":
            logger.log(
                "INFO",
                "Result",
                "Hasil Rollback: CANCELLED - Parameter PasswordAuthentication tidak ditemukan di sshd_config.",
            )
            sys.exit(0)

        # 2. Jika parameter terkomentar (#) -> Batalkan rollback
        if state == "commented":
            logger.log(
                "INFO",
                "Result",
                "Hasil Rollback: CANCELLED - Parameter PasswordAuthentication dalam keadaan terkomentar (#).",
            )
            sys.exit(0)

        # 3. Jika parameter sudah bernilai 'yes' -> Batalkan rollback
        if state == "active" and value and value.lower() == "yes":
            logger.log(
                "INFO",
                "Result",
                "Hasil Rollback: CANCELLED - PasswordAuthentication sudah bernilai 'yes'.",
            )
            sys.exit(0)

        # Penanganan jika parameter aktif tapi nilainya bukan 'no' (misal nilai kustom/tidak valid)
        if state == "active" and value and value.lower() != "no":
            logger.log(
                "WARNING",
                "Result",
                f"Hasil Rollback: CANCELLED - PasswordAuthentication bernilai '{value}' (hanya 'no' yang diubah ke 'yes').",
            )
            sys.exit(0)

        # 4. Jika parameter bernilai 'no' -> Ubah nilainya menjadi 'yes'
        with tempfile.NamedTemporaryFile(
            "w+", delete=False, prefix="sshd_config_"
        ) as tmp_file:
            tmp_config_path = Path(tmp_file.name)
            apply_rollback_logic(SSHD_CONFIG, tmp_file)

        # Validasi sintaks file sementara menggunakan sshd -t -f
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
                    "Hasil Rollback: SUCCEED - PasswordAuthentication berhasil dikembalikan ke 'yes'.",
                )
            else:
                logger.log(
                    "WARNING",
                    "Result",
                    "Hasil Rollback: WARNING - Konfigurasi diubah ke 'yes', tetapi gagal merestart service SSH.",
                )
        else:
            if tmp_config_path.exists():
                tmp_config_path.unlink()
            logger.log(
                "ERROR",
                "Result",
                "Hasil Rollback: CANCELLED - Sintaks konfigurasi invalid! Rollback dibatalkan.",
            )
            sys.exit(1)

    except Exception as e:
        logger.log(
            "ERROR",
            "Note",
            f"Terjadi error saat rollback K02: {e}"
        )
        logger.log(
            "FAILED",
            "Result",
            "Hasil Rollback: FAILED - Terjadi kesalahan pada proses rollback."
        )
        sys.exit(1)

    finally:
        release_lock(lock_file_obj)


if __name__ == "__main__":
    main()