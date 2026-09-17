from __future__ import annotations
from pathlib import Path
from typing import Optional, Tuple
import subprocess
import sys

# Import modul catalogutils via sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]  # Naik 3 level ke yoru-agent/

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.catalogutils import (
    SSHD_CONFIG,
    BaseLogger,
    acquire_lock_sshd,
    get_non_root_users,
    check_sshd_config_exists,
    release_lock,
)


def check_ssh_key_validity(key_file: Path) -> Tuple[bool, str]:
    """Mengecek keabsahan kunci publik SSH menggunakan ssh-keygen -l."""
    try:
        result = subprocess.run(
            ["ssh-keygen", "-l", "-f", str(key_file)],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return True, "Key valid"
        return False, result.stderr.strip()
    except Exception as e:
        return False, str(e)


def check_password_auth_status() -> Optional[str]:
    """Mengecek status PasswordAuthentication aktif di sshd_config (mengabaikan komentar)."""
    if not SSHD_CONFIG.is_file():
        return None

    with open(SSHD_CONFIG, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line_stripped = line.strip()
            if not line_stripped.startswith("#") and line_stripped.lower().startswith("passwordauthentication"):
                parts = line_stripped.split()
                if len(parts) >= 2:
                    return parts[1].lower()
    return None


def main():

    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="audit.json",
        catalog="K02",
        cis_id="5.2.14",
        log_type="audit",
    )
    
    lock_file = acquire_lock_sshd(logger)
    audit_passed = True
    
    try:
        if not check_sshd_config_exists(logger):
            logger.log(
                "FAILED", 
                "Result", 
                "Hasil Audit: FAILED - File sshd_config tidak ditemukan."
            )
            sys.exit(1)

        # Pastikan sudah memiliki daftar user non-root
        users_with_home = get_non_root_users(include_home=True)
        if not users_with_home:
            logger.log(
                "WARNING",
                "Note",
                "Tidak ditemukan user non-root dengan shell aktif di sistem.",
            )
            audit_passed = False
        else:
            user_list_str = ", ".join([u[0] for u in users_with_home])
            logger.log(
                "INFO",
                "Note",
                f"Ditemukan {len(users_with_home)} user non-root aktif: {user_list_str}"
            )

        # Verifikasi SSH Key setiap user
        for username, home_dir in users_with_home:
            auth_keys_path = home_dir / ".ssh" / "authorized_keys"

            # Check 2: Keberadaan public key
            if not auth_keys_path.is_file() or auth_keys_path.stat().st_size == 0:
                logger.log(
                    "ERROR",
                    "Note",
                    f"User '{username}' tidak memiliki file authorized_keys yang valid.",
                )
                audit_passed = False
                continue

            # Check 3: Validasi format key (ssh-keygen -l)
            is_valid, err_msg = check_ssh_key_validity(auth_keys_path)
            if not is_valid:
                logger.log(
                    "ERROR",
                    "Note",
                    f"File authorized_keys milik user '{username}' corrupt/tidak valid: {err_msg}",
                )
                audit_passed = False

            # Check 4: Permission file harus 600 (rw-------)
            file_mode = oct(auth_keys_path.stat().st_mode & 0o777)
            if file_mode != "0o600":
                logger.log(
                    "ERROR",
                    "Note",
                    f"Permission file authorized_keys user '{username}' adalah {file_mode} (Wajib 0o600).",
                )
                audit_passed = False

       
        # Cek Konfigurasi PasswordAuthentication saat ini
        pass_auth_status = check_password_auth_status()
        if pass_auth_status != "no":
            logger.log(
                "WARNING",
                "Note",
                f"Parameter PasswordAuthentication bernilai '{pass_auth_status or 'default (yes)'}' (Seharusnya 'no').",
            )
            audit_passed = False

        # Kesimpulan Audit
        if audit_passed:
            logger.log(
                "COMPLIANT",
                "Result",
                "Hasil Audit: COMPLIANT - Seluruh user non-root memiliki SSH key valid (permission 600) dan PasswordAuthentication di-set ke 'no'.",
            )
        else:
            logger.log(
                "NON_COMPLIANT",
                "Result",
                "Hasil Audit: NON_COMPLIANT - Terdapat syarat SSH Key atau konfigurasi SSHD yang belum terpenuhi.",
            )

    except Exception as e:
        logger.log_error("K02", "audit", e)

    finally:
        release_lock(lock_file)


if __name__ == "__main__":
    main()