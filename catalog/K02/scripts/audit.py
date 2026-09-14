from __future__ import annotations
from datetime import datetime
import fcntl
import json
import os
from pathlib import Path
import pwd
import subprocess
import sys
from typing import List, Optional, Tuple

# Konfigurasi Path
SCRIPT_DIR = Path(__file__).resolve().parent
LOG_DIR = SCRIPT_DIR.parent / "logs"
LOG_FILE = LOG_DIR / "audit.json"
SSHD_CONFIG = Path("/etc/ssh/sshd_config")
LOCK_FILE = Path("/tmp/sshd_config.lock")


def get_next_log_id() -> int:
    if LOG_FILE.exists():
        with open(LOG_FILE, "r", encoding="utf-8") as f:
            return sum(1 for _ in f) + 1
    return 1


class Logger:
    
    def __init__(self, log_path: Path):
        self.log_path = log_path
        self.log_path.parent.mkdir(parents=True, exist_ok=True)
        self.current_id = get_next_log_id()

    def log(
        self, level: str, message: str
    ) -> None:
        print(f"[{level}] {message}")

        log_entry = {
            "id": self.current_id,
            "timestamp": datetime.now().astimezone().isoformat(),
            "catalog": "K02",
            "cis_id": "5.2.14",
            "type":"audit",
            "level": level,
            "message": message,
        }

        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

        self.current_id += 1


def acquire_lock(lock_file_path: Path, logger: Logger):
    """Mencegah bentrokan eksekusi dengan skrip lain."""
    try:
        lock_file = open(lock_file_path, "w")
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return lock_file
    except (BlockingIOError, OSError):
        logger.log(
            "ERROR",
            "File sshd_config sedang diakses oleh proses lain. Audit dibatalkan.",
        )
        sys.exit(1)


def get_non_root_users() -> List[Tuple[str, Path]]:
    """Mendapatkan daftar user non-root (UID >= 1000) yang memiliki login shell aktif."""
    valid_users = []
    invalid_shells = {"/bin/false", "/usr/sbin/nologin", "/sbin/nologin", "/bin/sync"}

    for user in pwd.getpwall():
        if user.pw_uid >= 1000 and user.pw_name != "nobody":
            if user.pw_shell not in invalid_shells:
                valid_users.append((user.pw_name, Path(user.pw_dir)))

    return valid_users


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
    logger = Logger(LOG_FILE)

    # Kunci eksekusi skrip (jika gagal, akan otomatis catat log ERROR)
    lock_file_obj = acquire_lock(LOCK_FILE, logger)

    try:
        audit_passed = True

        # Pastikan sudah memiliki daftar user non-root
        non_root_users = get_non_root_users()
        if not non_root_users:
            logger.log(
                "WARNING",
                "Tidak ditemukan user non-root dengan shell aktif di sistem.",
            )
            audit_passed = False
        else:
            user_list_str = ", ".join([u[0] for u in non_root_users])
            logger.log(
                "INFO",
                f"Ditemukan user non-root aktif: {user_list_str}",
            )

        # Verifikasi SSH Key setiap user
        for username, home_dir in non_root_users:
            auth_keys_path = home_dir / ".ssh" / "authorized_keys"

            # Check 2: Keberadaan public key
            if not auth_keys_path.is_file() or auth_keys_path.stat().st_size == 0:
                logger.log(
                    "ERROR",
                    f"User '{username}' tidak memiliki file authorized_keys yang valid.",
                )
                audit_passed = False
                continue

            # Check 3: Validasi format key (ssh-keygen -l)
            is_valid, err_msg = check_ssh_key_validity(auth_keys_path)
            if not is_valid:
                logger.log(
                    "ERROR",
                    f"File authorized_keys milik user '{username}' corrupt/tidak valid: {err_msg}",
                )
                audit_passed = False

            # Check 4: Permission file harus 600 (rw-------)
            file_mode = oct(auth_keys_path.stat().st_mode & 0o777)
            if file_mode != "0o600":
                logger.log(
                    "ERROR",
                    f"Permission file authorized_keys user '{username}' adalah {file_mode} (Wajib 0o600).",
                )
                audit_passed = False

       
        # Cek Konfigurasi PasswordAuthentication saat ini
        pass_auth_status = check_password_auth_status()
        if pass_auth_status != "no":
            logger.log(
                "WARNING",
                f"Parameter PasswordAuthentication bernilai '{pass_auth_status or 'default (yes)'}' (Seharusnya 'no').",
            )
            audit_passed = False

        # -------------------------------------------------------------
        # KESIMPULAN AUDIT
        # -------------------------------------------------------------
        if audit_passed:
            logger.log(
                "SUCCESS",
                "audit_completed",
                "compliant",
                "Sistem COMPLIANT: Seluruh user non-root memiliki SSH key valid (permission 600) dan PasswordAuthentication di-set ke 'no'.",
            )
        else:
            logger.log(
                "WARNING",
                "audit_completed",
                "non_compliant",
                "Sistem NON-COMPLIANT: Terdapat syarat SSH Key atau konfigurasi SSHD yang belum terpenuhi.",
            )

        logger.log("INFO", "audit_end", "completed", "Proses audit selesai.")

    finally:
        fcntl.flock(lock_file_obj, fcntl.LOCK_UN)
        lock_file_obj.close()


if __name__ == "__main__":
    main()