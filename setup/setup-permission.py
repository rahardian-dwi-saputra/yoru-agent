from __future__ import annotations
from pathlib import Path
import os
import pwd
import subprocess
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import (
    SSHD_CONFIG,
    SSH_BACKUP_DIR,
    JOURNALD_CONFIG,
    JOURNALD_BACKUP_DIR,
    JOURNAL_LOG_DIR,
    JOURNAL_ACCESS_BACKUP,
    SYSCTL_CONF,
)


TARGET_USER = "yoru-agent"
DIRECTORY_MODE = 0o750
CONFIG_DIRECTORY_MODE = 0o755
CONFIG_FILE_MODE = 0o640


def run_command(
    command: list[str],
    timeout: int = 10,
) -> tuple[bool, str]:
    """Menjalankan perintah sistem dengan batas waktu."""

    try:
        result = subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )

        return True, result.stdout.strip()

    except subprocess.TimeoutExpired:
        return False, f"Perintah melebihi batas waktu ({timeout} detik)."

    except subprocess.CalledProcessError as exc:
        error = exc.stderr.strip() if exc.stderr else str(exc)
        return False, error

    except OSError as exc:
        return False, str(exc)


def configure_directory(
    directory: Path,
    uid: int,
    gid: int,
    mode: int = DIRECTORY_MODE,
) -> None:
    """Membuat direktori dan mengatur ownership serta permission."""

    directory.mkdir(
        parents=True,
        exist_ok=True,
        mode=mode,
    )

    os.chown(directory, uid, gid)
    directory.chmod(mode)


def configure_system_directory(
    directory: Path,
    mode: int = CONFIG_DIRECTORY_MODE,
) -> None:
    """Membuat direktori sistem tanpa mengubah ownership."""

    directory.mkdir(
        parents=True,
        exist_ok=True,
        mode=mode,
    )

    directory.chmod(mode)


def configure_file_access(
    file_path: Path,
    username: str,
    permission: str = "r",
) -> None:
    """Memberikan akses ACL kepada user aplikasi."""

    if not file_path.is_file():
        raise FileNotFoundError(
            f"File tidak ditemukan: {file_path}"
        )

    success, output = run_command(
        [
            "setfacl",
            "-m",
            f"u:{username}:{permission}",
            str(file_path),
        ],
        timeout=5,
    )

    if not success:
        raise RuntimeError(
            f"Gagal mengatur ACL {file_path}: {output}"
        )


def main() -> None:
    """Mempersiapkan direktori dan akses file Yoru-Agent."""

    if os.geteuid() != 0:
        print("ERROR: Script harus dijalankan sebagai root atau menggunakan sudo.")
        return

    try:
        user_info = pwd.getpwnam(TARGET_USER)

        print(
            f"Mengonfigurasi akses untuk {TARGET_USER} "
            f"(UID: {user_info.pw_uid})."
        )

        # Direktori milik user aplikasi.
        application_directories = (
            SSH_BACKUP_DIR,
            JOURNALD_BACKUP_DIR,
            JOURNAL_ACCESS_BACKUP.parent,
        )

        for directory in application_directories:
            configure_directory(
                directory,
                user_info.pw_uid,
                user_info.pw_gid,
            )

            print(f"OK: Direktori aplikasi: {directory}")

        # Direktori konfigurasi sistem.
        configure_system_directory(
            JOURNALD_CONFIG.parent,
            SYSCTL_CONF.parent,
        )

        print(f"OK: Direktori konfigurasi: {JOURNALD_CONFIG.parent}")

        # Memastikan direktori log tersedia tanpa mengubah ownership.
        if not JOURNAL_LOG_DIR.exists():
            configure_system_directory(
                JOURNAL_LOG_DIR
            )

            print(f"OK: Direktori log dibuat: {JOURNAL_LOG_DIR}")

        # Memberikan akses baca konfigurasi SSH.
        configure_file_access(
            SSHD_CONFIG,
            TARGET_USER,
        )

        # Memberikan akses baca konfigurasi journald jika sudah tersedia.
        if JOURNALD_CONFIG.is_file():
            configure_file_access(
                JOURNALD_CONFIG,
                TARGET_USER,
            )

        print("SUCCESS: Konfigurasi direktori dan akses berhasil.")

    except KeyError:
        print(f"ERROR: User '{TARGET_USER}' tidak ditemukan.")

    except (OSError, RuntimeError) as exc:
        print(f"ERROR: Gagal mengonfigurasi sistem: {exc}")

    except Exception as exc:
        print(f"ERROR: Terjadi kesalahan tidak terduga: {exc}")


if __name__ == "__main__":
    main()
