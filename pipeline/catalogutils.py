from __future__ import annotations
from typing import List, Optional, TextIO, Tuple, Union
from datetime import datetime
from pathlib import Path
import fcntl
import json
import os
import pwd
import subprocess
import sys
import uuid
import shutil

from config.settings import SSHD_CONFIG, INVALID_SHELLS, SSH_BACKUP_DIR

class BaseLogger:
    def __init__(
        self,
        script_dir: Path,
        log_file_name: str,
        catalog: str,
        cis_id: str,
        log_type: str,
    ) -> None:
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
            "execution_id": self.execution_id,
            "pid": os.getpid(),
            "timestamp": now.isoformat(),
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
        exception: Exception,
    ) -> None:
        self.log(
            "ERROR",
            "Note",
            f"Terjadi error saat {proses} {catalog}: {exception}",
        )
        self.log(
            "FAILED",
            "Result",
            f"Hasil {proses.capitalize()}: FAILED - Terjadi kesalahan pada proses {proses}.",
        )


def check_sshd_config_exists(
    logger: BaseLogger | None = None,
    config_path: Path = SSHD_CONFIG,
) -> bool:
    """Mengecek apakah file sshd_config ada dan merupakan file valid."""
    if not config_path.is_file():
        if logger:
            logger.log(
                "ERROR",
                "Note",
                f"File konfigurasi {config_path} tidak ditemukan.",
            )
        return False
    return True


def create_ssh_backup(logger=None) -> tuple[bool, str]:
    """
    Membuat file backup untuk sshd_config di dalam SSH_BACKUP_DIR.
    Memanfaatkan check_sshd_config_exists untuk validasi awal.
    Jika file backup sudah ada, fungsi akan langsung mengembalikan status True 
    tanpa membuat duplikasi file baru.
    """
    try:
        # Validasi keberadaan file sshd_config menggunakan fungsi yang ada
        if not check_sshd_config_exists(logger=logger, config_path=SSHD_CONFIG):
            msg = f"File konfigurasi SSH utama tidak ditemukan di {SSHD_CONFIG}"
            return False, msg

        # Pastikan direktori backup tersedia
        SSH_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        
        # Target path untuk file backup utama (misal: sshd_config.bak)
        backup_file = SSH_BACKUP_DIR / "sshd_config.bak"

        # Jika backup sudah ada, jangan buat duplikasi (kembalikan True)
        if backup_file.exists():
            msg = f"Backup sshd_config sudah tersedia di {backup_file} (menggunakan file yang ada)."
            return True, msg

        # Lakukan penyalinan file sebagai backup awal
        shutil.copy2(SSHD_CONFIG, backup_file)
        
        # Tambahan timestamp versioning opsional jika ingin rekam jejak historis
        timestamp_str = datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%d_%H%M%S")
        timestamp_backup = SSH_BACKUP_DIR / f"sshd_config_{timestamp_str}.bak"
        shutil.copy2(SSHD_CONFIG, timestamp_backup)

        msg = f"Backup sshd_config berhasil dibuat di {backup_file}."
        return True, msg

    except Exception as e:
        err_msg = f"Gagal membuat backup SSH: {str(e)}"
        if logger:
            logger.log_error("SYSTEM", "backup", e)
        return False, err_msg


def restart_ssh_service() -> bool:
    """Mencoba merestart service sshd atau ssh."""
    for service in ["sshd", "ssh"]:
        result = subprocess.run(
            ["systemctl", "restart", service], capture_output=True
        )
        if result.returncode == 0:
            return True
    return False


def acquire_lock(lock_name: str, logger: BaseLogger | None = None) -> Optional[TextIO]:
    """Mengambil lock eksklusif non-blocking berdasarkan nama lock."""
    lock_path = Path(f"/tmp/{lock_name}.lock")
    try:
        lock_file = open(lock_path, "w")
        fcntl.flock(lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return lock_file
    except (BlockingIOError, OSError):
        if logger:
            logger.log(
                "SKIPPED",
                "Result",
                f"Proses audit/remediasi '{lock_name}' sedang berjalan di proses lain. Eksekusi dibatalkan.",
            )
        sys.exit(0)


def acquire_lock_sshd(logger: BaseLogger | None = None) -> Optional[TextIO]:
    """Shortcut pengunci untuk proses sshd_config."""
    return acquire_lock("sshd_config", logger)


def acquire_lock_ufw(logger: BaseLogger | None = None) -> Optional[TextIO]:
    """Shortcut pengunci untuk proses UFW."""
    return acquire_lock("ufw_audit", logger)


def release_lock(lock_file_obj: Optional[TextIO]) -> None:
    """Melepaskan lock dan menutup file handle."""
    if lock_file_obj:
        try:
            fcntl.flock(lock_file_obj, fcntl.LOCK_UN)
            lock_file_obj.close()
        except Exception:
            pass


def get_non_root_users(
    include_home: bool = False,
) -> Union[List[str], List[Tuple[str, Path]]]:
    """Mendapatkan daftar user non-root aktif (UID >= 1000)."""
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