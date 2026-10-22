from __future__ import annotations
from typing import List, Optional, TextIO, Tuple, Union
from datetime import datetime, timezone
from pathlib import Path
import fcntl
import json
import os
import pwd
import subprocess
import sys
import uuid
import shutil
import filecmp
import getpass
import socket

from config.settings import (
    TIMEZONE_NAME,
    APP_TIMEZONE,
    SSHD_CONFIG,
    SSH_SERVICE_NAME, 
    INVALID_SHELLS, 
    SSH_BACKUP_DIR, 
    JOURNALD_CONFIG, 
    JOURNALD_BACKUP_DIR,
    JOURNALD_SERVICE_NAME
)


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

    def _send_to_journal(self, status: str, step: str, message: str) -> None:
        """
        Fungsi internal untuk mengirim log ke Linux System Journal via utilitas 'logger'.
        Tag diset ke 'yoru-agent' agar mudah difilter nanti.
        """
        try:
            # Bersihkan pesan dari baris baru agar format syslog rapi
            clean_msg = message.replace("\n", " ").strip()
            
            # Format pesan yang akan dikirim ke journal
            syslog_msg = f"[{self.catalog} | CIS {self.cis_id}] Type: {self.log_type.upper()} | Status: {status} | Step: {step} | {clean_msg}"
            
            # Pemetaan prioritas syslog yang mencakup seluruh status (Audit, Hardening, Rollback)
            priority = "daemon.info"
            
            if status in ["ERROR", "FAILED"]:
                priority = "daemon.err"
            elif status in ["WARNING"]:
                priority = "daemon.warning" 
            elif status in ["SUCCESS", "COMPLIANT"]:
                priority = "daemon.notice"  # Untuk hasil sukses atau compliant yang positif
            elif status in ["NON_COMPLIANT"]:
                priority = "daemon.warning" # Non-compliant pada audit berarti butuh perhatian (warning)
            elif status in ["SKIPPED"]:
                priority = "daemon.info"    # Dilewati secara normal/aman

            # Eksekusi perintah bawaan Linux: logger -t yoru-agent -p [prioritas] [pesan]
            subprocess.run(
                ["logger", "-t", "yoru-agent", "-p", priority, syslog_msg],
                capture_output=True,
                check=False
            )
        except Exception:
            pass
        
    def log(self, status: str, step: str, message: str) -> None:
        now = datetime.now(APP_TIMEZONE)
        unique_log_id = f"log-{now.strftime('%Y%m%d%H%M%S%f')}-{os.getpid()}-{uuid.uuid4().hex[:4]}"

        log_entry = {
            "id": unique_log_id,
            "execution_id": self.execution_id,
            "timestamp": now.isoformat(),
            "timezone": TIMEZONE_NAME,
            "pid": os.getpid(),
            "hostname": socket.gethostname(),
            "executed_by": getpass.getuser(),
            
            "catalog": self.catalog,
            "cis_id": self.cis_id,
            "type": self.log_type,

            "status": status,
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


def release_lock(lock_file_obj: Optional[TextIO]) -> None:
    """Melepaskan lock dan menutup file handle."""
    if lock_file_obj:
        try:
            fcntl.flock(lock_file_obj, fcntl.LOCK_UN)
            lock_file_obj.close()
        except Exception:
            pass


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
    Hanya membuat backup baru (ber-timestamp) jika file asli mengalami perubahan 
    dibandingkan backup terakhir.
    """
    try:
        if not check_sshd_config_exists(logger=logger, config_path=SSHD_CONFIG):
            msg = f"File konfigurasi SSH utama tidak ditemukan di {SSHD_CONFIG}"
            return False, msg

        SSH_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        backup_file = SSH_BACKUP_DIR / "sshd_config.bak"

        # Jika backup utama belum ada sama sekali, buat baru
        if not backup_file.exists():
            shutil.copy2(SSHD_CONFIG, backup_file)
            msg = f"Backup awal sshd_config berhasil dibuat di {backup_file}."
            if logger:
                logger.log("SUCCESS", "BackupCreated", msg)
            return True, msg

        # Jika backup sudah ada, bandingkan apakah file asli sudah berubah (diff)
        # filecmp.cmp mengembalikan True jika isi kedua file persis sama
        if filecmp.cmp(SSHD_CONFIG, backup_file, shallow=False):
            msg = "Konfigurasi SSH tidak berubah. Menggunakan backup yang sudah ada."
            return True, msg

        # Jika isi file BERUBAH, buat versioning timestamp baru sebagai arsip historis
        timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        versioned_backup = SSH_BACKUP_DIR / f"sshd_config_{timestamp_str}.bak"
        shutil.copy2(SSHD_CONFIG, versioned_backup)
        
        # Perbarui juga file backup utama
        shutil.copy2(SSHD_CONFIG, backup_file)

        msg = f"Perubahan terdeteksi pada sshd_config. Backup historis dibuat: {versioned_backup.name}"
        if logger:
            logger.log("SUCCESS", "BackupVersioned", msg)
        return True, msg

    except Exception as e:
        err_msg = f"Gagal membuat backup SSH: {str(e)}"
        if logger:
            logger.log_error("SYSTEM", "backup", e)
        return False, err_msg


def restart_ssh_service() -> bool:
    """Mencoba merestart service sshd atau ssh."""
    services_to_try = [SSH_SERVICE_NAME, "sshd", "ssh"]
    services_to_try = list(dict.fromkeys(services_to_try))

    for service in services_to_try:
        result = subprocess.run(
            ["systemctl", "restart", service], capture_output=True
        )
        if result.returncode == 0:
            return True
    return False


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


def check_journald_config_exists(
    logger: BaseLogger | None = None,
    config_path: Path = JOURNALD_CONFIG,
) -> bool:
    """Mengecek apakah file journald.conf ada dan merupakan file valid."""
    if not config_path.is_file():
        if logger:
            logger.log(
                "ERROR",
                "Note",
                f"File konfigurasi {config_path} tidak ditemukan.",
            )
        return False
    return True


def parse_size_to_bytes(size_str: str) -> int:
    """
    Mengubah string ukuran systemd (misal: '500M', '2G', '1024K', '1048576') 
    menjadi bentuk integer dalam satuan Bytes.
    """
    size_str = size_str.strip().upper()
    multiplier = 1
    
    if size_str.endswith('K'):
        multiplier = 1024
        size_str = size_str[:-1]
    elif size_str.endswith('M'):
        multiplier = 1024 * 1024
        size_str = size_str[:-1]
    elif size_str.endswith('G'):
        multiplier = 1024 * 1024 * 1024
        size_str = size_str[:-1]
    elif size_str.endswith('T'):
        multiplier = 1024 * 1024 * 1024 * 1024
        size_str = size_str[:-1]
        
    try:
        return int(float(size_str) * multiplier)
    except ValueError:
        return 0


def check_journald_disk_space_prerequisite(target_max_use_str: str, logger=None) -> bool:
    """
    Prasyarat: Memeriksa apakah sisa disk di /var/log minimal 3x dari nilai SystemMaxUse yang akan dipasang.
    """
    try:
        max_bytes = parse_size_to_bytes(target_max_use_str)
        if max_bytes == 0:
            return True # Jika parsing gagal, lewati validasi ukuran untuk menghindari false positive

        required_space = max_bytes * 3
        usage = shutil.disk_usage("/var/log")

        if usage.free < required_space:
            if logger:
                logger.log(
                    "WARNING",
                    "PreFlightCheck",
                    f"Peringatan Disk: Sisa ruang /var/log ({usage.free} bytes) kurang dari 3x SystemMaxUse yang diminta ({required_space} bytes)."
                )
            return False
        return True
    except Exception as e:
        if logger:
            logger.log_error("SYSTEM", "disk_check", e)
        return True


def create_journald_backup(logger=None) -> Tuple[bool, str]:
    """Membuat backup versioned untuk journald.conf mirip dengan skrip SSH."""
    try:
        if not JOURNALD_CONFIG.is_file():
            return False, f"File konfigurasi journald tidak ditemukan di {JOURNALD_CONFIG}"

        JOURNALD_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        backup_file = JOURNALD_BACKUP_DIR / "journald.conf.bak"

        if not backup_file.exists():
            shutil.copy2(JOURNALD_CONFIG, backup_file)
            msg = f"Backup awal journald.conf berhasil dibuat di {backup_file}."
            if logger:
                logger.log("SUCCESS", "BackupCreated", msg)
            return True, msg

        # Jika isi file sama persis, gunakan yang sudah ada
        if filecmp.cmp(JOURNALD_CONFIG, backup_file, shallow=False):
            return True, "Konfigurasi journald tidak berubah. Menggunakan backup yang sudah ada."

        # Jika berubah, buat versi timestamp historis
        from datetime import datetime, timezone
        timestamp_str = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        versioned_backup = JOURNALD_BACKUP_DIR / f"journald.conf_{timestamp_str}.bak"
        shutil.copy2(JOURNALD_CONFIG, versioned_backup)
        shutil.copy2(JOURNALD_CONFIG, backup_file)

        msg = f"Perubahan terdeteksi pada journald.conf. Backup historis dibuat: {versioned_backup.name}"
        if logger:
            logger.log("SUCCESS", "BackupVersioned", msg)
        return True, msg

    except Exception as e:
        err_msg = f"Gagal membuat backup journald: {str(e)}"
        if logger:
            logger.log_error("SYSTEM", "backup", e)
        return False, err_msg


def restart_journald_service() -> bool:
    """
    Fungsi terpusat untuk merestart service systemd-journald.
    """
    try:
        res = subprocess.run(
            ["systemctl", "restart", JOURNALD_SERVICE_NAME],
            capture_output=True,
            text=True,
            check=False,
        )
        return res.returncode == 0
    except Exception:
        return False