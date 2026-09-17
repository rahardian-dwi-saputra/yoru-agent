from __future__ import annotations
from datetime import datetime
from pathlib import Path
from typing import List, Tuple, Union
from typing import Optional, TextIO
import fcntl
import json
import sys
import uuid
import os
import subprocess
import pwd

# Path Konfigurasi sistem
SSHD_CONFIG = Path("/etc/ssh/sshd_config")
LOCK_FILE = Path("/tmp/sshd_config.lock")
LOCK_FILE_UFW = Path("/tmp/ufw_audit.lock")
PASSWD_FILE = Path("/etc/passwd")

VALID_SHELLS = {"/bin/bash", "/bin/sh", "/bin/zsh"}
INVALID_SHELLS = {"/bin/false", "/usr/sbin/nologin", "/sbin/nologin", "/bin/sync"}

def check_sshd_config_exists(
    logger: BaseLogger | None = None, 
    config_path: Path = SSHD_CONFIG
) -> bool:
    """Mengecek apakah file sshd_config ada dan merupakan file valid.

    Jika logger diberikan dan file tidak ada, pesan ERROR akan otomatis dicatat.
    """
    if not config_path.is_file():
        if logger:
            logger.log(
                "ERROR",
                "Note", 
                f"File konfigurasi {config_path} tidak ditemukan."
            )
        return False
    return True

def restart_ssh_service() -> bool:
    """Mencoba merestart service sshd atau ssh."""
    for service in ["sshd", "ssh"]:
        result = subprocess.run(
            ["systemctl", "restart", service], capture_output=True
        )
        if result.returncode == 0:
            return True
    return False

class BaseLogger:

    def __init__(
        self,
        script_dir: Path,
        log_file_name: str,
        catalog: str,
        cis_id: str,
        log_type: str,
    ):
       
        self.catalog_dir = script_dir.parent
        self.log_dir = self.catalog_dir / "logs"
        self.log_path = self.log_dir / log_file_name

        # Buat folder logs jika belum ada
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

        self.catalog = catalog
        self.cis_id = cis_id
        self.log_type = log_type
        self.execution_id = f"exec-{uuid.uuid4().hex[:8]}"

    def log(self, level: str, step: str, message: str) -> None:
        now = datetime.now().astimezone()
        unique_log_id = f"log-{now.strftime('%Y%m%d%H%M%S%f')}-{os.getpid()}-{uuid.uuid4().hex[:4]}"

        log_entry = {
            "id": unique_log_id,
            "execution_id": self.execution_id,  # Kode unik per sesi eksekusi
            "pid": os.getpid(),
            "timestamp": datetime.now().astimezone().isoformat(),
            "catalog": self.catalog,
            "cis_id": self.cis_id,
            "type": self.log_type,
            "level": level,
            "step": step,
            "message": message,
        }

        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(log_entry, ensure_ascii=False) + "\n")

    def log_error(
            self,
            catalog: str, 
            proses: str, 
            exception: Exception
        ):
       
        self.log(
            "ERROR",
            "Note",
            f"Terjadi error saat {proses} {catalog}: {exception}"
        )
    
        self.log(
            "FAILED",
            "Result",
            f"Hasil {proses.capitalize()}: FAILED - Terjadi kesalahan pada proses {proses}."
        )


def acquire_lock(logger: BaseLogger):
    try:
        lock_file = open(LOCK_FILE, "w")
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return lock_file
    except (BlockingIOError, OSError):
        logger.log(
            "ERROR",
            "Note",
            "File sshd_config sedang diakses oleh proses lain. Operasi dibatalkan.",
        )
        sys.exit(1)


def acquire_lock_ufw(logger: BaseLogger):
    try:
        lock_file = open(LOCK_FILE_UFW, "w")
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return lock_file
    except (BlockingIOError, OSError):
        logger.log(
            "ERROR",
            "Note",
            "File UFW sedang diakses oleh proses lain. Operasi dibatalkan.",
        )
        sys.exit(1)

def acquire_lock2(lock_name: str, logger=None) -> Optional[TextIO]:
    """Mengambil lock eksklusif non-blocking berdasarkan nama lock."""
    lock_path = Path(f"/tmp/{lock_name}.lock")
    try:
        lock_file = open(lock_path, "w")
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return lock_file
    except (BlockingIOError, IOError):
        if logger:
            logger.log(
                "SKIPPED",
                "Result",
                f"Proses audit/remediasi '{lock_name}' sedang berjalan. Eksekusi dibatalkan.",
            )
        sys.exit(0)

def release_lock(lock_file_obj) -> None:
    if lock_file_obj:
        fcntl.flock(lock_file_obj, fcntl.LOCK_UN)
        lock_file_obj.close()


def get_non_root_users(include_home: bool = False) -> Union[List[str], List[Tuple[str, Path]]]:
    """Mendapatkan daftar user non-root aktif (UID >= 1000).
    
    Args:
        include_home: Jika True, mengembalikan List[Tuple[username, home_dir]].
                      Jika False, hanya mengembalikan List[username].
    """
    valid_users = []
    for user in pwd.getpwall():
        if user.pw_uid >= 1000 and user.pw_name != "nobody":
            if user.pw_shell not in INVALID_SHELLS:
                if include_home:
                    valid_users.append((user.pw_name, Path(user.pw_dir)))
                else:
                    valid_users.append(user.pw_name)

    return valid_users


def is_ufw_installed() -> bool:
    """Memeriksa apakah paket UFW terinstall pada sistem Debian/Ubuntu."""
    try:
        res = subprocess.run(
            ["dpkg-query", "-s", "ufw"],
            capture_output=True,
            text=True,
        )
        return res.returncode == 0 and "Status: install ok installed" in res.stdout
    except Exception:
        return False