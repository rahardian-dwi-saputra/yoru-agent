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
    get_non_root_users,
    release_lock,
    restart_ssh_service,
)


def check_file_permissions(config_path: Path, expected_mode: int = 0o600) -> bool:
    """Mengecek apakah permission file bernilai 600 (rw-------)."""
    if not config_path.exists():
        return False
    # Mengambil bit izin file (st_mode & 0o777)
    file_stat = config_path.stat()
    file_mode = file_stat.st_mode & 0o777
    return file_mode == expected_mode


def has_valid_ssh_key(home_dir: Path) -> bool:
    """Mengecek keberadaan file authorized_keys yang tidak kosong pada user."""
    ssh_dir = home_dir / ".ssh"
    auth_keys = ssh_dir / "authorized_keys"

    if not auth_keys.is_file():
        return False

    # Pastikan file authorized_keys tidak kosong dan memiliki minimal 1 baris kunci valid
    try:
        with open(auth_keys, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line_stripped = line.strip()
                if line_stripped and not line_stripped.startswith("#"):
                    return True
    except OSError:
        return False

    return False


def get_current_password_auth_status(config_path: Path) -> Tuple[str, Optional[str]]:
    """Mengecek status dan nilai PasswordAuthentication di sshd_config.

    Return:
        Tuple[state, value]
        - state: 'not_found', 'commented', 'active'
        - value: Nilai parameter (misal 'yes', 'no') atau None
    """
    if not config_path.is_file():
        return "not_found", None

    with open(config_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line_stripped = line.strip()

            # Baris Terkomentar
            if line_stripped.startswith("#"):
                uncommented = line_stripped[1:].lstrip()
                if uncommented.lower().startswith("passwordauthentication"):
                    parts = uncommented.split()
                    val = parts[1] if len(parts) >= 2 else None
                    return "commented", val

            # Baris Aktif
            elif line_stripped.lower().startswith("passwordauthentication"):
                parts = line_stripped.split()
                val = parts[1] if len(parts) >= 2 else None
                return "active", val

    return "not_found", None


def apply_password_auth_logic(
    src_path: Path, dst_file_obj
) -> Tuple[bool, str]:
    """Menerapkan logika manipulasi PasswordAuthentication ke file sementara."""
    found_parameter = False
    action_taken = ""

    with open(src_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line_stripped = line.strip()

            # 1. Parameter terkomentar -> uncomment dan ubah ke 'no'
            if line_stripped.startswith("#"):
                uncommented = line_stripped[1:].lstrip()
                if uncommented.lower().startswith("passwordauthentication"):
                    found_parameter = True
                    dst_file_obj.write("PasswordAuthentication no\n")
                    action_taken = "uncommented_and_set_to_no"
                    continue

            # 2. Parameter aktif -> ubah nilainya ke 'no'
            elif line_stripped.lower().startswith("passwordauthentication"):
                found_parameter = True
                dst_file_obj.write("PasswordAuthentication no\n")
                action_taken = "updated_to_no"
                continue

            dst_file_obj.write(line)

    # 3. Parameter belum ada -> tambahkan di akhir file
    if not found_parameter:
        dst_file_obj.write("\nPasswordAuthentication no\n")
        action_taken = "appended_new_parameter"

    return found_parameter, action_taken


def main():
    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="hardening.json",
        catalog="K02",
        cis_id="5.2.14",
        log_type="hardening",
    )

    lock_file = acquire_lock(logger)

    try:
        if not check_sshd_config_exists(logger):
            logger.log(
                "FAILED", 
                "Result", 
                "Hasil Hardening: FAILED - File sshd_config tidak ditemukan."
            )
            sys.exit(1)

        # Cek Permission file sshd_config (Harus 600)
        if not check_file_permissions(SSHD_CONFIG, 0o600):
            file_mode = oct(SSHD_CONFIG.stat().st_mode & 0o777)
            logger.log(
                "FAILED",
                "Result",
                f"Hasil Hardening: CANCELLED - Permission file {SSHD_CONFIG} adalah {file_mode} (harus 0600).",
            )
            sys.exit(1)

        # Cek User Non-Root dan SSH Key Valid
        non_root_users = get_non_root_users(include_home=True)

        if not non_root_users:
            logger.log(
                "FAILED",
                "Result",
                "Hasil Hardening: CANCELLED FOR SECURITY REASONS - Tidak ditemukan user non-root aktif di sistem!",
            )
            sys.exit(1)

        # Filter user yang memiliki SSH Key valid di authorized_keys
        users_with_key = [
            user for user, home in non_root_users if has_valid_ssh_key(home)
        ]

        if not users_with_key:
            logger.log(
                "FAILED",
                "Result",
                "Hasil Hardening: CANCELLED FOR SECURITY REASONS - Tidak ada user non-root yang memiliki SSH Key valid (~/.ssh/authorized_keys)!",
            )
            sys.exit(1)

        logger.log(
            "INFO",
            "Note",
            f"Verifikasi user berhasil: Ditemukan {len(users_with_key)} user non-root dengan SSH Key valid ({', '.join(users_with_key)}).",
        )

        # Cek Nilai PasswordAuthentication Saat Ini
        state, value = get_current_password_auth_status(SSHD_CONFIG)

        if state == "active" and value and value.lower() == "no":
            logger.log(
                "SKIPPED",
                "Result",
                "Hasil Hardening: SKIPPED - Parameter PasswordAuthentication sudah bernilai 'no'.",
            )
            sys.exit(0)

        with tempfile.NamedTemporaryFile(
            "w+", delete=False, prefix="sshd_config_"
        ) as tmp_file:
            tmp_config_path = Path(tmp_file.name)
            _, action = apply_password_auth_logic(SSHD_CONFIG, tmp_file)

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
                    f"Hardening berhasil: SUCCEED - PasswordAuthentication berhasil DINONAKTIFKAN (Aksi: {action}).",
                )
            else:
                logger.log(
                    "WARNING",
                    "Result",
                    "Hardening berhasil: WARNING - Konfigurasi diubah, tetapi gagal merestart service SSH.",
                )
        else:
            if tmp_config_path.exists():
                tmp_config_path.unlink()
            logger.log(
                "FAILED",
                "Result",
                "Hardening berhasil: FAILED - Sintaks konfigurasi invalid! Hardening dibatalkan.",
            )
            sys.exit(1)

    except Exception as e:
        logger.log_error("K02", "hardening", e)

    finally:
        release_lock(lock_file)


if __name__ == "__main__":
    main()