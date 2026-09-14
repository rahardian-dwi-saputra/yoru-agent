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
)


def get_current_root_login_status() -> Optional[str]:
    """Mengecek status PermitRootLogin saat ini di sshd_config."""
    if not SSHD_CONFIG.is_file():
        return None

    with open(SSHD_CONFIG, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line_stripped = line.strip()
            if line_stripped.startswith("#"):
                continue

            if line_stripped.lower().startswith("permitrootlogin"):
                parts = line_stripped.split()
                if len(parts) >= 2:
                    return parts[1]
    return None


def apply_permit_root_login_logic(
    src_path: Path, dst_file_obj
) -> Tuple[bool, str]:
    """Menerapkan logika manipulasi PermitRootLogin ke dalam file sementara."""
    found_parameter = False
    action_taken = ""

    with open(src_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line_stripped = line.strip()

            # 1. Baris Komentar: e.g. #PermitRootLogin yes / # PermitRootLogin no
            if line_stripped.startswith("#"):
                uncommented = line_stripped[1:].lstrip()
                if uncommented.lower().startswith("permitrootlogin"):
                    found_parameter = True
                    dst_file_obj.write("PermitRootLogin no\n")
                    action_taken = "uncommented_and_set_to_no"
                    continue

            # 2. Baris Aktif: e.g. PermitRootLogin yes / PermitRootLogin prohibit-password
            elif line_stripped.lower().startswith("permitrootlogin"):
                found_parameter = True
                dst_file_obj.write("PermitRootLogin no\n")
                action_taken = "updated_to_no"
                continue

            # Tulis baris lain tanpa perubahan
            dst_file_obj.write(line)

    # 3. Parameter Belum Ada Sama Sekali
    if not found_parameter:
        dst_file_obj.write("\nPermitRootLogin no\n")
        action_taken = "appended_new_parameter"

    return found_parameter, action_taken


def restart_ssh_service() -> bool:
    """Mencoba merestart service sshd atau ssh."""
    for service in ["sshd", "ssh"]:
        result = subprocess.run(
            ["systemctl", "restart", service], capture_output=True
        )
        if result.returncode == 0:
            return True
    return False


def main():
    
    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="hardening.json",
        catalog="K01",
        cis_id="5.1.20",
        log_type="hardening",
    )

    # Kunci eksekusi skrip
    lock_file_obj = acquire_lock(logger)

    try:
        if not check_sshd_config_exists(logger):
            logger.log(
                "FAILED", 
                "Result", 
                "Hasil Hardening: FAILED - File sshd_config tidak ditemukan."
            )
            sys.exit(1)

        # Cek A: Apakah Root login sudah disabled?
        current_status = get_current_root_login_status()
        if current_status and current_status.lower() == "no":
            logger.log(
                "INFO",
                "Result",
                "Hasil Hardening: Dibatalkan - Root login SSH sudah dalam keadaan nonaktif (PermitRootLogin no).",
            )
            sys.exit(0)

        # Cek B: Apakah ada user non-root lain yang bisa login?
        other_users_count = len(get_non_root_users())
        if other_users_count == 0:
            logger.log(
                "ERROR",
                "Result",
                "Hasil Hardening: Dibatalkan demi keamanan - Tidak ditemukan user non-root dengan akses shell!",
            )
            sys.exit(1)

        logger.log(
            "INFO",
            "Note",
            f"Verifikasi berhasil: Ditemukan {other_users_count} user non-root aktif.",
        )

        with tempfile.NamedTemporaryFile(
            "w+", delete=False, prefix="sshd_config_"
        ) as tmp_file:
            tmp_config_path = Path(tmp_file.name)

            found_param, action = apply_permit_root_login_logic(
                SSHD_CONFIG, tmp_file
            )

        # Validasi sintaks file sementara menggunakan sshd -t -f
        validate_cmd = subprocess.run(
            ["sshd", "-t", "-f", str(tmp_config_path)], capture_output=True
        )

        if validate_cmd.returncode == 0:
            # Timpa file utama secara atomic
            shutil.move(str(tmp_config_path), str(SSHD_CONFIG))
            os.chmod(SSHD_CONFIG, 0o600)

            if restart_ssh_service():
                logger.log(
                    "SUCCESS",
                    "Result",
                    f"Hasil Hardening: Berhasil - Root login via SSH berhasil DINONAKTIFKAN (Aksi: {action}).",
                )
            else:
                logger.log(
                    "WARNING",
                    "Result",
                    "Hasil Hardening: Konfigurasi sudah diubah, tetapi gagal merestart service SSH.",
                )
        else:
            if tmp_config_path.exists():
                tmp_config_path.unlink()
            logger.log(
                "ERROR",
                "Result",
                "Hasil Hardening: Sintaks konfigurasi invalid! Hardening dibatalkan.",
            )
            sys.exit(1)

    except Exception as e:
        logger.log(
            "ERROR",
            "Note", 
            f"Terjadi error saat proses hardening: {e}"
        )
        logger.log(
            "FAILED",
            "Result",
            "Hasil Hardening: FAILED - Terjadi kesalahan pada proses hardening."
        )
        sys.exit(1)

    finally:
        # Melepaskan penguncian file
        release_lock(lock_file_obj)


if __name__ == "__main__":
    main()