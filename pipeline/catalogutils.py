from __future__ import annotations
from datetime import datetime
from pathlib import Path
from typing import List
import fcntl
import json
import sys
import uuid
import os

# Path Konfigurasi sistem
SSHD_CONFIG = Path("/etc/ssh/sshd_config")
LOCK_FILE = Path("/tmp/sshd_config.lock")
PASSWD_FILE = Path("/etc/passwd")

VALID_SHELLS = {"/bin/bash", "/bin/sh", "/bin/zsh"}

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

        self.current_id += 1


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


def release_lock(lock_file_obj) -> None:
    if lock_file_obj:
        fcntl.flock(lock_file_obj, fcntl.LOCK_UN)
        lock_file_obj.close()


def get_non_root_users() -> List[str]:
    non_root_users = []
    if not PASSWD_FILE.exists():
        return non_root_users

    with open(PASSWD_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            parts = line.split(":")
            if len(parts) >= 7:
                username, shell = parts[0], parts[6]
                if username != "root" and shell in VALID_SHELLS:
                    non_root_users.append(username)

    return non_root_users