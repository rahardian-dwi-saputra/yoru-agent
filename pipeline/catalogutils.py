from __future__ import annotations
from typing import Literal, List, Optional, TextIO, Tuple, Union, Callable
from datetime import datetime, timezone
from pathlib import Path
from enum import Enum
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
import stat
import yaml
import re
import tempfile


from config.settings import (
    TIMEZONE_NAME,
    APP_TIMEZONE,
    SSHD_CONFIG,
    INVALID_SHELLS, 
    SSH_BACKUP_DIR
)

class LogStatus(str, Enum):
    """Status log operasional Yoru-Agent."""

    INFO = "INFO"
    SUCCESS = "SUCCESS"
    COMPLIANT = "COMPLIANT"
    WARNING = "WARNING"
    NON_COMPLIANT = "NON_COMPLIANT"
    ERROR = "ERROR"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"

class BaseLogger:
    """Logger terpusat Yoru-Agent untuk file JSON dan Linux System Journal."""

    SYSLOG_TAG = "yoru-agent"

    SYSLOG_PRIORITIES = {
        "ERROR": "daemon.err",
        "FAILED": "daemon.err",
        "WARNING": "daemon.warning",
        "NON_COMPLIANT": "daemon.warning",
        "SUCCESS": "daemon.notice",
        "COMPLIANT": "daemon.notice",
        "SKIPPED": "daemon.info",
    }

    def __init__(
        self,
        script_dir: Path,
        log_file_name: str,
        catalog: str,
        nama: str,
        kode_cis: str,
        judul_cis: str,
        versi_cis: str,
        regulasi: str,
        kepatuhan: str,
        log_type: str,
        *,
        max_bytes: int = 10 * 1024 * 1024,
        backup_count: int = 3,
        journal_timeout: float = 5.0,
        journal_error_callback: Callable[[str], None] | None = None,
    ) -> None:

        if (
            not log_file_name
            or Path(log_file_name).name != log_file_name
            or log_file_name in {".", ".."}
        ):
            raise ValueError("Nama file log tidak valid.")

        if max_bytes <= 0 or backup_count < 0:
            raise ValueError("Konfigurasi rotasi log tidak valid.")

        if journal_timeout <= 0:
            raise ValueError("journal_timeout harus lebih besar dari nol.")
        
        self.catalog_dir = script_dir.parent
        self.log_dir = self.catalog_dir / "logs"
        self.log_path = self.log_dir / log_file_name
        self.lock_path = self.log_dir / f".{log_file_name}.lock"

        # Buat folder logs jika belum ada
        self.log_dir.mkdir(
            parents=True, 
            exist_ok=True, 
            mode=0o700
        )

        self.catalog = catalog
        self.nama = nama
        self.kode_cis = kode_cis
        self.judul_cis = judul_cis
        self.versi_cis = versi_cis
        self.regulasi = regulasi
        self.kepatuhan = kepatuhan
        self.log_type = log_type
        self.execution_id = f"exec-{uuid.uuid4().hex[:8]}"

        self.max_bytes = max_bytes
        self.backup_count = backup_count
        self.journal_timeout = journal_timeout
        self.journal_error_callback = journal_error_callback
        self.journal_failures = 0

        self._secure_file(self.lock_path)
        self._secure_file(self.log_path)

    @staticmethod
    def _secure_file(path: Path) -> None:
        """Buat atau amankan file agar hanya dapat diakses pemiliknya."""

        flags = os.O_CREAT | os.O_RDWR
        flags |= getattr(os, "O_NOFOLLOW", 0)

        fd = os.open(path, flags, 0o600)

        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise OSError(f"Bukan file reguler: {path}")

            os.fchmod(fd, 0o600)
        finally:
            os.close(fd)

    @staticmethod
    def _normalize_status(status: str | LogStatus) -> str:
        """Validasi status log."""

        value = status.value if isinstance(status, LogStatus) else status

        if not isinstance(value, str):
            raise TypeError("Status harus berupa string atau LogStatus.")

        value = value.strip().upper()

        try:
            return LogStatus(value).value
        except ValueError as exc:
            raise ValueError(f"Status log tidak valid: {value}") from exc

    def _rotate(self) -> None:
        """Rotasi file berdasarkan ukuran; pemanggil harus memegang lock."""

        if not self.log_path.exists():
            return

        if self.log_path.stat().st_size < self.max_bytes:
            return

        if self.backup_count == 0:
            with self.log_path.open("w", encoding="utf-8"):
                pass
            os.chmod(self.log_path, 0o600)
            return

        oldest = self.log_path.with_name(
            f"{self.log_path.name}.{self.backup_count}"
        )
        oldest.unlink(missing_ok=True)

        for number in range(self.backup_count - 1, 0, -1):
            source = self.log_path.with_name(
                f"{self.log_path.name}.{number}"
            )
            target = self.log_path.with_name(
                f"{self.log_path.name}.{number + 1}"
            )

            if source.exists():
                os.replace(source, target)

        os.replace(
            self.log_path,
            self.log_path.with_name(f"{self.log_path.name}.1"),
        )

    def _write_json(self, entry: dict) -> None:
        """Tulis satu baris JSON secara tersinkronisasi antarproses."""

        data = (
            json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n"
        ).encode("utf-8")

        lock_fd = os.open(self.lock_path, os.O_RDWR)

        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)

            self._rotate()

            flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT
            flags |= getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(self.log_path, flags, 0o600)

            try:
                if not __import__("stat").S_ISREG(os.fstat(fd).st_mode):
                    raise OSError("Target log bukan file reguler.")

                os.fchmod(fd, 0o600)

                with os.fdopen(fd, "ab", closefd=False) as log_file:
                    log_file.write(data)
                    log_file.flush()
                    os.fsync(log_file.fileno())
            finally:
                os.close(fd)
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)

    def _send_to_journal(self, entry: dict) -> bool:
        """Kirim log ke Linux System Journal menggunakan utilitas logger."""

        duration_str = (
            f" | Durasi: {entry['duration_ms']:.4f} ms"
            if entry.get("duration_ms") is not None
            else ""
        )
        
        message = (
            f"[{entry['catalog']} | " 
            f"Nama: {entry['nama']}] | "
            f"Kode CIS: {entry['kode_cis']}] | "
            f"Judul CIS: {entry['judul_cis']}] | "
            f"Versi CIS: {entry['versi_cis']}] | "
            f"Regulasi: {entry['regulasi']} | "
            f"Kepatuhan: {entry['kepatuhan']} | "
            f"Type: {entry['type']} | "
            f"Status: {entry['status']} | "
            f"Step: {entry['step']} | {entry['message']}"
            f"{duration_str}"
            f" ]"
        )

        priority = self.SYSLOG_PRIORITIES.get(
            entry["status"], "daemon.info"
        )
        
        try:
            # Eksekusi perintah bawaan Linux: logger -t yoru-agent -p [prioritas] [pesan]
            result = subprocess.run(
                [
                    "logger", "-t", self.SYSLOG_TAG,
                    "-p", priority, "--", message,
                ],
                capture_output=True,
                check=False,
                timeout=self.journal_timeout,
            )

            if result.returncode == 0:
                return True

            reason = f"logger exit code: {result.returncode}"

        except (OSError, subprocess.TimeoutExpired) as exc:
            reason = type(exc).__name__

        self.journal_failures += 1

        if self.journal_error_callback:
            try:
                self.journal_error_callback(reason)
            except Exception:
                pass

        return False

    def log(
            self, 
            status: str | LogStatus, 
            step: str, 
            message: str,
            *,
            duration_ms: float | None = None
        ) -> None:
        """Simpan log ke file JSON dan teruskan ke Linux System Journal."""

        status = self._normalize_status(status)

        now = datetime.now(APP_TIMEZONE)

        unique_log_id = (
            f"log-{now.strftime('%Y%m%d%H%M%S%f')}-"
            f"{os.getpid()}-{uuid.uuid4().hex[:4]}"
        )

        log_entry = {
            "id": unique_log_id,
            "execution_id": self.execution_id,
            "timestamp": now.isoformat(),
            "timezone": TIMEZONE_NAME,
            "pid": os.getpid(),
            "hostname": socket.gethostname(),
            "executed_by": getpass.getuser(),
            "catalog": self.catalog,
            "nama": self.nama,
            "kode_cis": self.kode_cis,
            "judul_cis": self.judul_cis,
            "versi_cis": self.versi_cis,
            "regulasi":self.regulasi,
            "kepatuhan":self.kepatuhan,
            "type": self.log_type,
            "status": status,
            "step": step,
            "message": message,
        }

        if duration_ms is not None:
            log_entry["duration_ms"] = round(duration_ms, 4)

        self._write_json(log_entry)

        # Kirim salinan log ke Linux System Journal
        self._send_to_journal(log_entry)

    def log_error(
        self,
        catalog: str,
        proses: str,
        exception: Exception,
        *,
        duration_ms: float | None = None,
    ) -> None:
        """Catat detail error dan hasil akhir proses yang gagal."""

        self.log(
            LogStatus.ERROR,
            "Result",
            f"Hasil {proses.capitalize()}: ERROR - Terjadi error saat {proses} {catalog} ( {type(exception).__name__} : {exception} )",
            duration_ms=duration_ms,
        )


# Mengambil nilai vars dari Taskfile.yml
def load_taskfile_vars(script_dir: Path) -> dict:
    """
    Membaca variabel metadata dari Taskfile.yml yang berada 
    satu tingkat di atas direktori scripts (level katalog Kxx).
    """
    taskfile_path = script_dir.parent / "Taskfile.yml"
    
    if not taskfile_path.is_file():
        return {}

    try:
        with open(taskfile_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
            return data.get("vars", {})
    except Exception:
        return {}

    
# Function untuk melakukan log file
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
                LogStatus.SKIPPED,
                "Result",
                f"Proses audit/remediasi '{lock_name}' sedang berjalan di proses lain. Eksekusi dibatalkan.",
            )
        sys.exit(0)


# Function untuk melepas log file
def release_lock(lock_file_obj: Optional[TextIO]) -> None:
    """Melepaskan lock dan menutup file handle."""
    if lock_file_obj:
        try:
            fcntl.flock(lock_file_obj, fcntl.LOCK_UN)
            lock_file_obj.close()
        except Exception:
            pass


# Function untuk mengecek keberadaan file konfigurasi
def check_config_exists(
    config_path: Path,
    config_name: str = "Konfigurasi",
    logger: BaseLogger | None = None,
) -> bool:
    """Mengecek apakah file konfigurasi generik ada dan merupakan file valid."""
    if not config_path.is_file():
        if logger:
            logger.log(
                LogStatus.ERROR,
                "Note",
                f"File {config_name} ({config_path}) tidak ditemukan atau tidak valid.",
            )
        return False
    return True


# Function ini mengecek parameter SSH via sshd -T
def get_effective_sshd_parameter(
    config_file: Path,
    parameter: str,
) -> str:
    """Mengambil nilai parameter dari konfigurasi efektif sshd."""

    sshd_path = shutil.which("sshd")

    if sshd_path is None:
        raise RuntimeError("Executable sshd tidak ditemukan.")

    try:
        result = subprocess.run(
            [
                sshd_path,
                "-T",
                "-f",
                str(config_file),
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("Proses pembacaan konfigurasi sshd (-T) mengalami timeout.")

    if result.returncode != 0:
        error_message = result.stderr.strip() or (
            "sshd -T gagal tanpa pesan error."
        )
        raise RuntimeError(
            f"Gagal membaca konfigurasi efektif sshd: {error_message}"
        )

    parameter = parameter.lower()

    for line in result.stdout.splitlines():
        key, _, value = line.partition(" ")

        if key.lower() == parameter:
            return value.strip().lower()

    raise RuntimeError(
        f"Parameter {parameter} tidak ditemukan pada output sshd -T."
    )


def get_effective_journald_parameter(parameter: str) -> str:
    """
    Membaca nilai parameter efektif systemd-journald, termasuk konfigurasi drop-in.
    """
    systemd_analyze = shutil.which("systemd-analyze")

    if not systemd_analyze:
        raise RuntimeError(
            "Executable systemd-analyze tidak ditemukan."
        )

    try:
        result = subprocess.run(
            [
                systemd_analyze,
                "cat-config",
                "systemd/journald.conf",
            ],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            "Pembacaan konfigurasi journald mengalami timeout."
        ) from exc

    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.strip()
            or "Gagal membaca konfigurasi journald."
        )

    value = None
    in_journal_section = False

    for line in result.stdout.splitlines():
        line = line.strip()

        # Awal file konfigurasi berikutnya.
        if re.match(r"^#\s+/(?:etc|run|usr)/", line):
            in_journal_section = False
            continue

        if not line or line.startswith("#"):
            continue

        # Hanya membaca section [Journal].
        if line.startswith("["):
            in_journal_section = line.lower() == "[journal]"
            continue

        if not in_journal_section or "=" not in line:
            continue

        key, _, current_value = line.partition("=")

        if key.strip().lower() == parameter.lower():
            value = current_value.strip()

    # Default Storage menurut systemd adalah auto.
    if value is None and parameter.lower() == "storage":
        return "auto"

    if value is None:
        raise RuntimeError(
            f"Parameter {parameter} tidak ditemukan."
        )

    return value



ParameterStatus = Literal["not_found", "commented", "active"]

def check_config_parameter_value(
    file_path: Path,
    param_name: str,
    comment_chars: tuple[str, ...] = ("#", ";"),
    case_sensitive: bool = False,
) -> Tuple[ParameterStatus, Optional[str]]:
    """
    Mengecek status keberadaan parameter dan mengambil nilai aktualnya jika aktif.
    
    Returns:
        Tuple[ParameterStatus, Optional[str]]: 
            - Status: "not_found" | "commented" | "active"
            - Nilai: string nilai parameter jika ditemukan aktif, atau None jika tidak ada/dikomentari.
    """
    if not file_path.is_file():
        return "not_found", None


    active_value: Optional[str] = None
    has_commented_version = False

    target_param = param_name if case_sensitive else param_name.lower()

    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                stripped_line = line.strip()
                if not stripped_line:
                    continue

                is_commented_line = stripped_line.startswith(comment_chars)
                content_to_check = stripped_line
                if is_commented_line:
                    content_to_check = stripped_line.lstrip("".join(comment_chars)).strip()

                # Pisahkan berdasarkan spasi atau tanda '=' (misal: "LoginGraceTime 1m" atau "LoginGraceTime=1m")
                # Kita ganti '=' dengan spasi agar mudah di-split
                normalized_line = content_to_check.replace("=", " ")
                parts = normalized_line.split()
                
                if not parts:
                    continue

                current_key = parts[0]
                if not case_sensitive:
                    current_key = current_key.lower()

                if current_key == target_param:
                    if not is_commented_line:
                        # Ambil nilai parameter (biasanya ada di indeks ke-1)
                        if len(parts) > 1:
                            active_value = parts[1]
                        return "active", active_value
                    else:
                        has_commented_version = True

        if has_commented_version:
            return "commented", None
        
        return "not_found", None

    except Exception:
        return "not_found", None


def set_config_parameter_value(
    file_path: Path,
    param_name: str,
    target_value: str,
    comment_chars: tuple[str, ...] = ("#", ";"),
    case_sensitive: bool = False,
) -> bool:
    """
    Mengubah, membuka komentar (uncomment), atau menambahkan parameter konfigurasi
    pada file berdasarkan statusnya (menggunakan referensi check_config_parameter_value).
    
    Args:
        file_path (Path): Path ke file konfigurasi.
        param_name (str): Nama parameter yang akan diatur.
        target_value (str): Nilai target baru untuk parameter tersebut.
        comment_chars (tuple[str, ...]): Karakter penanda komentar.
        case_sensitive (bool): Apakah pencarian key bersifat case-sensitive.
        
    Returns:
        bool: True jika berhasil memperbarui/menambahkan file, False jika gagal.
    """
    if not file_path.is_file():
        return False

    # 1. Cek status parameter menggunakan fungsi referensi
    status, _ = check_config_parameter_value(
        file_path, param_name, comment_chars, case_sensitive
    )

    target_key = param_name if case_sensitive else param_name.lower()
    updated_lines: list[str] = []
    param_updated = False

    try:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                stripped_line = line.strip()
                
                # Jika baris kosong, biarkan apa adanya
                if not stripped_line:
                    updated_lines.append(line)
                    continue

                is_commented_line = stripped_line.startswith(comment_chars)
                content_to_check = stripped_line
                if is_commented_line:
                    content_to_check = stripped_line.lstrip("".join(comment_chars)).strip()

                normalized_line = content_to_check.replace("=", " ")
                parts = normalized_line.split()

                if parts:
                    current_key = parts[0]
                    if not case_sensitive:
                        current_key = current_key.lower()

                    # Jika baris ini cocok dengan target parameter (baik aktif maupun commented)
                    if current_key == target_key:
                        # Tangani kasus active atau commented: update nilainya dan pastikan di-uncomment
                        indent = line[: len(line) - len(line.lstrip())]
                        updated_lines.append(f"{indent}{param_name} {target_value}\n")
                        param_updated = True
                        continue

                updated_lines.append(line)

        # 2. Jika status awalnya 'not_found' dan belum sempat diperbarui, tambahkan di baris paling bawah
        if not param_updated and status == "not_found":
            if updated_lines and not updated_lines[-1].endswith("\n"):
                updated_lines.append("\n")
            updated_lines.append(f"{param_name} {target_value}\n")

        # 3. Tulis ulang file konfigurasi dengan perubahan
        with open(file_path, "w", encoding="utf-8") as f:
            f.writelines(updated_lines)

        return True

    except Exception:
        return False

    
def is_package_installed(package_name: str, binary_name: str | None = None) -> bool:
    """Memeriksa apakah paket atau binary sudah terinstal pada sistem."""

    target_binary = binary_name or package_name

    # Periksa keberadaan binary melalui PATH.
    if shutil.which(target_binary):
        return True

    # Periksa status instalasi paket menggunakan dpkg.
    try:
        result = subprocess.run(
            [
                "dpkg-query",
                "-W",
                "-f=${Status}",
                package_name,
            ],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

        return (
            result.returncode == 0
            and result.stdout.strip() == "install ok installed"
        )

    except (OSError, subprocess.TimeoutExpired):
        return False



ServiceState = Literal["running", "stopped", "failed", "unknown"]
ServiceEnableState = Literal["enabled", "disabled", "masked", "unknown"]

def check_systemd_service_status(service_name: str) -> Tuple[bool, ServiceState, ServiceEnableState]:
    """
    Mengecek status aktif (running) dan enable dari suatu layanan systemd.
    
    Args:
        service_name: Nama layanan systemd (contoh: "ssh", "ufw", "auditd", "nginx")
        
    Returns:
        Tuple[bool, ServiceState, ServiceEnableState]:
            - is_active_and_enabled: True jika layanan aktif (running) DAN enabled, False jika sebaliknya.
            - active_status: Status runtime ("running", "stopped", "failed", "unknown")
            - enable_status: Status startup ("enabled", "disabled", "masked", "unknown")
    """

    active_state: ServiceState = "unknown"
    enable_state: ServiceEnableState = "unknown"

    try:
        # Periksa status runtime service.
        result = subprocess.run(
            ["systemctl", "is-active", service_name],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

        active_output = result.stdout.strip()

        active_state = {
            "active": "running",
            "inactive": "stopped",
            "dead": "stopped",
            "failed": "failed",
        }.get(active_output, "unknown")

        # Periksa status startup service.
        result = subprocess.run(
            ["systemctl", "is-enabled", service_name],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )

        enable_output = result.stdout.strip()

        enable_state = {
            "enabled": "enabled",
            "disabled": "disabled",
            "masked": "masked",
        }.get(enable_output, "unknown")

    except (OSError, subprocess.TimeoutExpired):
        return False, "unknown", "unknown"

    is_compliant = (
        active_state == "running"
        and enable_state == "enabled"
    )

    return is_compliant, active_state, enable_state


def create_ssh_backup(logger=None) -> tuple[bool, str]:
    """
    Membuat file backup untuk sshd_config di dalam SSH_BACKUP_DIR.
    Hanya membuat backup baru (ber-timestamp) jika file asli mengalami perubahan 
    dibandingkan backup terakhir.
    """
    try:
        if not check_config_exists(config_path=SSHD_CONFIG, config_name="sshd_config", logger=logger):
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


def restart_system_service(service_names: Union[str, List[str]]) -> bool:
    """
    Merestart satu atau beberapa layanan systemd.
    
    Args:
        service_names: Nama service (string) atau daftar nama service (list of strings).
        
    Returns:
        bool: True jika restart berhasil, False jika semua percobaan gagal.
    """
  
    if isinstance(service_names, str):
        services = [service_names]
    elif isinstance(service_names, list):
        services = service_names
    else:
        return False

    # Hapus duplikat jika ada, sambil mempertahankan urutan
    services = list(dict.fromkeys(
        service.strip()
        for service in services
        if isinstance(service, str) and service.strip()
    ))

    systemctl = shutil.which("systemctl")
    if not systemctl:
        return False

    for service in services:
        try:
            result = subprocess.run(
                ["systemctl", "restart", service],
                capture_output=True,
                text=True,
                timeout=30,
                check=False
            )
            
            if result.returncode == 0:
                return True
        except (subprocess.TimeoutExpired, OSError):
            continue

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


def check_journald_access(
    log_dir: Path,
) -> tuple[bool, str]:
    """Memeriksa keamanan permission direktori dan file log journald."""

    if not log_dir.exists():
        return (
            True,
            "Direktori log journald belum tersedia (volatile mode).",
        )

    try:
        paths = [log_dir, *log_dir.rglob("*")]

        for path in paths:
            file_stat = path.lstat()

            if not (
                stat.S_ISDIR(file_stat.st_mode)
                or stat.S_ISREG(file_stat.st_mode)
            ):
                continue

            mode = file_stat.st_mode

            if path == log_dir:
                if mode & stat.S_IWOTH:
                    return (
                        False,
                        f"Direktori {path} memiliki permission world-writable.",
                    )
            elif mode & (stat.S_IWGRP | stat.S_IWOTH):
                return (
                    False,
                    f"Objek {path} memiliki permission group/world-writable.",
                )

        return (
            True,
            "Permission direktori dan file log journald sudah aman.",
        )

    except OSError as exc:
        return False, f"Gagal memeriksa permission log journald: {exc}"



def run_command(command: list[str], timeout: int = 30) -> subprocess.CompletedProcess:
    """Menjalankan perintah sistem dengan timeout dan validasi error."""
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"Perintah {' '.join(command)} mengalami timeout."
        ) from exc
    except OSError as exc:
        raise RuntimeError(
            f"Gagal menjalankan perintah {' '.join(command)}: {exc}"
        ) from exc

    if result.returncode != 0:
        error_message = result.stderr.strip() or "Tidak ada pesan error."
        raise RuntimeError(
            f"Perintah {' '.join(command)} gagal: {error_message}"
        )

    return result


def get_runtime_sysctl_value(sysctl_key: str, timeout: int = 30) -> str:
    """Mengambil nilai runtime parameter sysctl."""
    
    sysctl_path = shutil.which("sysctl")
    if not sysctl_path:
        raise RuntimeError("Executable sysctl tidak ditemukan.")

    result = run_command([
        sysctl_path,
        "-n",
        sysctl_key,
    ], timeout=timeout)

    value = result.stdout.strip()
    if not value:
        raise RuntimeError(
            f"Nilai runtime {sysctl_key} kosong."
        )
    return value

def get_persistent_sysctl_value(sysctl_key: str, timeout: int = 30) -> str | None:
    """Mengambil nilai konfigurasi persisten sysctl dari sysctl.d dan /etc/sysctl.conf."""
    
    systemd_analyze_path = shutil.which("systemd-analyze")
    if not systemd_analyze_path:
        raise RuntimeError("Executable systemd-analyze tidak ditemukan.")

    result = run_command([
        systemd_analyze_path,
        "cat-config",
        "sysctl.d",
    ], timeout=timeout)

    config_text = result.stdout
    sysctl_conf = Path("/etc/sysctl.conf")

    if sysctl_conf.exists():
        try:
            config_text += "\n" + sysctl_conf.read_text(encoding="utf-8")
        except OSError as exc:
            raise RuntimeError(f"Gagal membaca {sysctl_conf}: {exc}") from exc

    persistent_value = None
    for line in config_text.splitlines():
        line = line.split("#", 1)[0].strip()
        if not line or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip().replace("/", ".")
        value = value.strip()

        if key == sysctl_key:
            if not value:
                raise RuntimeError(f"Konfigurasi {sysctl_key} memiliki nilai kosong.")
            persistent_value = value

    return persistent_value


def write_config_atomically(
    config_file: Path,
    content: str | bytes,
    mode: int = 0o644,
) -> None:
    """Menulis konfigurasi secara atomik untuk menghindari file parsial."""
    config_file.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=config_file.parent,
            prefix=f".{config_file.name}.",
            suffix=".tmp",
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            if isinstance(content, str):
                content = content.encode("utf-8")
            temp_file.write(content)
            temp_file.flush()
            os.fsync(temp_file.fileno())

        os.chmod(temp_path, mode)
        os.replace(temp_path, config_file)
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


def get_config_mode(config_file: Path) -> int:
    """
    Mengambil permission file konfigurasi dengan validasi keamanan 
    untuk mencegah symbolic link dan memastikan berupa file biasa.
    """
    if config_file.is_symlink():
        raise RuntimeError(
            f"File konfigurasi tidak boleh berupa symbolic link: {config_file}"
        )

    if config_file.exists():
        if not config_file.is_file():
            raise RuntimeError(
                f"Path konfigurasi bukan file biasa: {config_file}"
            )
        return stat.S_IMODE(config_file.stat().st_mode)

    return 0o644


def restore_config(
    config_file: Path,
    original_content: bytes | None,
    original_mode: int,
    sysctl_path: str,
) -> None:
    """
    Mengembalikan konfigurasi awal file (atau menghapusnya jika aslinya belum ada) 
    serta menerapkan ulang perintah sysctl --system.
    """
    if original_content is None:
        if config_file.exists():
            config_file.unlink()
    else:
        write_config_atomically(
            config_file,
            original_content,
            original_mode,
        )

    run_command([sysctl_path, "--system"])