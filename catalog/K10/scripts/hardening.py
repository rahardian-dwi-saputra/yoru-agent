from __future__ import annotations
from pathlib import Path
from time import perf_counter
import sys
import os
import shutil
import subprocess

# Import modul catalogutils via sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]  # Naik 3 level ke yoru-agent/

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import (
    JOURNALD_CONFIG, 
    JOURNALD_BACKUP_DIR,
    JOURNAL_LOG_DIR,
    JOURNALD_SERVICE_NAME,
    CATALOG_LOCKS
)

from pipeline.catalogutils import (
    LogStatus,
    BaseLogger,
    load_taskfile_vars,
    acquire_lock,
    release_lock,
    get_effective_journald_parameter,
    restart_system_service
)

def backup_configuration() -> bool:
    """
    Membuat backup konfigurasi.

    Returns:
        True jika file konfigurasi sebelumnya tersedia.
        False jika file belum tersedia.
    """
    JOURNALD_BACKUP_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    backup_file = JOURNALD_BACKUP_DIR / JOURNALD_CONFIG.name

    if JOURNALD_CONFIG.is_file():
        shutil.copy2(JOURNALD_CONFIG, backup_file)
        return True

    return False

def apply_configuration() -> None:
    """Menerapkan konfigurasi Storage=persistent."""

    JOURNALD_CONFIG.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    content = (
        "[Journal]\n"
        "Storage=persistent\n"
    )

    temp_config = JOURNALD_CONFIG.with_name(
        f".{JOURNALD_CONFIG.name}.tmp"
    )

    try:
        temp_config.write_text(
            content,
            encoding="utf-8",
        )

        os.chmod(temp_config, 0o644)
        os.replace(temp_config, JOURNALD_CONFIG)

    finally:
        temp_config.unlink(missing_ok=True)

def run_command(command: list[str]) -> None:
    """Menjalankan command sistem dan menangani kegagalan."""

    executable = shutil.which(command[0])

    if not executable:
        raise RuntimeError(
            f"Executable {command[0]} tidak ditemukan."
        )

    command[0] = executable

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"Command {' '.join(command)} mengalami timeout."
        ) from exc

    if result.returncode != 0:
        raise RuntimeError(
            result.stderr.strip()
            or f"Command {' '.join(command)} gagal."
        )

def restore_configuration(original_exists: bool) -> None:
    """Memulihkan konfigurasi jika hardening gagal."""

    backup_file = JOURNALD_BACKUP_DIR / JOURNALD_CONFIG.name

    if original_exists:
        if not backup_file.is_file():
            raise RuntimeError(
                "Backup konfigurasi tidak ditemukan."
            )

        shutil.copy2(backup_file, JOURNALD_CONFIG)

    else:
        JOURNALD_CONFIG.unlink(missing_ok=True)

    
def main():
    task_vars = load_taskfile_vars(SCRIPT_DIR)

    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="hardening.json",
        catalog=task_vars.get("ID", "K10"),
        nama=task_vars.get("NAMA", "Penyimpanan Log Journald Permanen"),
        kode_cis=task_vars.get("KODE_CIS", "6.1.2.4"),
        judul_cis=task_vars.get("JUDUL_CIS", "Ensure journald Storage is configured"),
        versi_cis=task_vars.get("VERSI_CIS", "Ubuntu 24.04 LTS Benchmark v2.0.0"),
        regulasi=task_vars.get("REGULASI", "Pasal 31, Pasal 35"),
        kepatuhan=task_vars.get("KEPATUHAN", "UU PDP No. 27/2022"),
        log_type="hardening",
    )

    lock_name = CATALOG_LOCKS.get("K10", "journald_audit")
    lock_file = acquire_lock(lock_name, logger)

    start = perf_counter()
    original_exists = False
    configuration_changed = False

    try:
        # Cek apakah Storage sudah dihardening
        storage = get_effective_journald_parameter("Storage").lower()

        if storage == "persistent":
            logger.log(
                LogStatus.SKIPPED,
                "Result",
                f"Hasil Hardening: SKIPPED - Konfigurasi Storage journald sudah bernilai 'persistent'",
                duration_ms=(perf_counter() - start) * 1000,
            )
            sys.exit(0)


        # Backup konfigurasi sebelumnya
        original_exists = backup_configuration()

        # Buat direktori penyimpanan permanen
        JOURNAL_LOG_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )

        # Terapkan konfigurasi
        apply_configuration()
        configuration_changed = True

        # Atur permission dan ownership direktori jurnal
        run_command([
            "systemd-tmpfiles",
            "--create",
            "--prefix",
            str(JOURNAL_LOG_DIR),
        ])

        if not restart_system_service(JOURNALD_SERVICE_NAME):
            raise RuntimeError(
                f"Gagal merestart service {JOURNALD_SERVICE_NAME}."
            )

        # Flush log runtime ke penyimpanan permanen
        run_command([
            "journalctl",
            "--flush",
        ])

        storage = get_effective_journald_parameter(
            "Storage"
        ).lower()

        if storage != "persistent":
            raise RuntimeError(
                f"Validasi gagal: Storage ditemukan '{storage}', diharapkan 'persistent'."
            )

        if not JOURNAL_LOG_DIR.is_dir():
            raise RuntimeError(
                f"Direktori {JOURNAL_LOG_DIR} tidak ditemukan."
            )

        # Pastikan layanan berjalan
        run_command([
            "systemctl",
            "is-active",
            "--quiet",
            JOURNALD_SERVICE_NAME,
        ])

        logger.log(
            LogStatus.SUCCESS,
            "Result",
            f"Hasil Hardening: SUCCEED - Storage=persistent berhasil diterapkan. dan service SSH berhasil direstart.",
            duration_ms=(perf_counter() - start) * 1000,
        )
        sys.exit(0)

    except Exception as e:
        if configuration_changed:
            try:
                restore_configuration(original_exists)

                restart_system_service(
                    JOURNALD_SERVICE_NAME
                )

            except Exception as rollback_error:
                logger.log_error(
                    "K10",
                    "hardening-restore",
                    rollback_error,
                )

        logger.log_error(
            "K10", 
            "hardening", 
            e,
            duration_ms=(perf_counter() - start) * 1000,
        )
        sys.exit(2)
    finally:
        release_lock(lock_file)


if __name__ == "__main__":
    main()