from __future__ import annotations
from pathlib import Path
from time import perf_counter
import sys
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
    restart_system_service,
)


def restore_configuration() -> bool:
    """
    Memulihkan konfigurasi journald sebelum hardening.

    Jika backup tersedia, konfigurasi asli dipulihkan.
    Jika backup tidak tersedia, drop-in K10 dihapus karena
    diasumsikan sebelumnya belum tersedia.

    Returns:
        True jika konfigurasi berhasil diubah.
        False jika tidak ada perubahan yang diperlukan.
    """
    backup_file = JOURNALD_BACKUP_DIR / JOURNALD_CONFIG.name

    # Pulihkan konfigurasi asli jika backup tersedia.
    if backup_file.is_file():
        JOURNALD_CONFIG.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        temp_config = JOURNALD_CONFIG.with_name(
            f".{JOURNALD_CONFIG.name}.restore"
        )

        try:
            shutil.copy2(backup_file, temp_config)
            temp_config.replace(JOURNALD_CONFIG)

        finally:
            temp_config.unlink(missing_ok=True)

        return True

    # Hapus drop-in jika sebelumnya belum tersedia.
    if JOURNALD_CONFIG.is_file():
        JOURNALD_CONFIG.unlink()
        return True

    return False


def run_command(command: list[str]) -> None:
    """Menjalankan command sistem dan menangani kegagalan."""

    if not command:
        raise ValueError("Command tidak boleh kosong.")

    executable = shutil.which(command[0])

    if not executable:
        raise RuntimeError(
            f"Executable {command[0]} tidak ditemukan."
        )

    command_args = [executable, *command[1:]]

    try:
        result = subprocess.run(
            command_args,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )

    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            f"Command {' '.join(command_args)} mengalami timeout."
        ) from exc

    except OSError as exc:
        raise RuntimeError(
            f"Gagal menjalankan command {' '.join(command_args)}: {exc}"
        ) from exc

    if result.returncode != 0:
        error_message = (
            result.stderr.strip()
            or result.stdout.strip()
            or f"Command {' '.join(command_args)} gagal."
        )

        raise RuntimeError(error_message)


def main():
    task_vars = load_taskfile_vars(SCRIPT_DIR)

    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="rollback.json",
        catalog=task_vars.get("ID", "K10"),
        nama=task_vars.get("NAMA", "Penyimpanan Log Journald Permanen"),
        kode_cis=task_vars.get("KODE_CIS", "6.1.2.4"),
        judul_cis=task_vars.get("JUDUL_CIS", "Ensure journald Storage is configured"),
        versi_cis=task_vars.get("VERSI_CIS", "Ubuntu 24.04 LTS Benchmark v2.0.0"),
        regulasi=task_vars.get("REGULASI", "Pasal 31, Pasal 35"),
        kepatuhan=task_vars.get("KEPATUHAN", "UU PDP No. 27/2022"),
        log_type="rollback",
    )

    lock_name = CATALOG_LOCKS.get("K10", "journald_audit")
    lock_file = acquire_lock(lock_name, logger)
    start = perf_counter()

    try:
        # Pulihkan konfigurasi sebelumnya.
        configuration_changed = restore_configuration()

        if not configuration_changed:
            logger.log(
                LogStatus.SKIPPED,
                "Result",
                "Hasil Rollback: SKIPPED - Tidak ditemukan konfigurasi K10 yang perlu dipulihkan.",
                duration_ms=(perf_counter() - start) * 1000,
            )
            return 0

        # Restart systemd-journald setelah pemulihan.
        if not restart_system_service(JOURNALD_SERVICE_NAME):
            raise RuntimeError(
                f"Gagal merestart service {JOURNALD_SERVICE_NAME}."
            )

        # Pastikan service berjalan.
        run_command([
            "systemctl",
            "is-active",
            "--quiet",
            JOURNALD_SERVICE_NAME,
        ])

        # Periksa konfigurasi Storage setelah rollback.
        storage = get_effective_journald_parameter(
            "Storage"
        ).lower()

        # Hapus backup setelah rollback berhasil.
        backup_file = JOURNALD_BACKUP_DIR / JOURNALD_CONFIG.name

        try:
            backup_file.unlink(missing_ok=True)

        except OSError as cleanup_error:
            logger.log_error(
                "K10",
                "rollback-cleanup",
                cleanup_error,
            )

        logger.log(
            LogStatus.SUCCESS,
            "Result",
            f"Hasil Rollback: SUCCESS - Konfigurasi berhasil dipulihkan. Storage saat ini bernilai '{storage}' dan service {JOURNALD_SERVICE_NAME} aktif.",
            duration_ms=(perf_counter() - start) * 1000,
        )

    except Exception as e:
        logger.log_error(
            "K10", 
            "rollback", 
            e,
            duration_ms=(perf_counter() - start) * 1000,
        )
        sys.exit(2)

    finally:
        release_lock(lock_file)


if __name__ == "__main__":
    main()