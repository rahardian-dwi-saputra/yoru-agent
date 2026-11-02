from __future__ import annotations
from pathlib import Path
from time import perf_counter
import sys
import stat
import tempfile
import os
import json

# Import modul catalogutils via sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]  # Naik 3 level ke yoru-agent/

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import (
    JOURNAL_LOG_DIR, 
    JOURNAL_ACCESS_BACKUP,
    CATALOG_LOCKS
)

from pipeline.catalogutils import (
    LogStatus,
    BaseLogger,
    load_taskfile_vars,
    acquire_lock,
    release_lock,
    check_journald_access
)


def create_journald_access_backup() -> tuple[bool, str]:
    """Menyimpan metadata permission dan ownership log journald."""

    if not JOURNAL_LOG_DIR.is_dir():
        return False, "Direktori log journald tidak ditemukan atau bukan direktori."

    backup_path = JOURNAL_ACCESS_BACKUP

    if backup_path.exists():
        return (
            False,
            f"Backup metadata sudah tersedia: {backup_path}. "
            "Rollback atau arsipkan backup sebelumnya terlebih dahulu.",
        )

    try:
        paths = [JOURNAL_LOG_DIR, *JOURNAL_LOG_DIR.rglob("*")]
        entries = []

        for path in paths:
            file_stat = path.lstat()

            if stat.S_ISDIR(file_stat.st_mode):
                object_type = "directory"
            elif stat.S_ISREG(file_stat.st_mode):
                object_type = "file"
            else:
                continue

            entries.append({
                "path": str(path.relative_to(JOURNAL_LOG_DIR)),
                "type": object_type,
                "mode": stat.S_IMODE(file_stat.st_mode),
                "uid": file_stat.st_uid,
                "gid": file_stat.st_gid,
            })

        backup_path.parent.mkdir(parents=True, exist_ok=True)

        backup_data = {
            "version": 1,
            "root": str(JOURNAL_LOG_DIR),
            "entries": entries,
        }

        # Tulis backup secara atomik agar tidak menghasilkan JSON parsial.
        fd, temp_path = tempfile.mkstemp(
            prefix="journald-access-",
            suffix=".tmp",
            dir=backup_path.parent,
        )

        try:
            with os.fdopen(fd, "w", encoding="utf-8") as file:
                json.dump(backup_data, file, indent=4)
                file.flush()
                os.fsync(file.fileno())

            os.chmod(temp_path, 0o600)
            os.replace(temp_path, backup_path)

        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

        return True, f"Backup metadata journald berhasil dibuat: {backup_path}."

    except (OSError, ValueError, TypeError) as exc:
        return False, f"Gagal membuat backup metadata journald: {exc}"


def main():
    task_vars = load_taskfile_vars(SCRIPT_DIR)

    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="hardening.json",
        catalog=task_vars.get("ID", "K09"),
        nama=task_vars.get("NAMA", "Pengaturan Akses File Log Journald"),
        kode_cis=task_vars.get("KODE_CIS", "6.1.1.2"),
        judul_cis=task_vars.get("JUDUL_CIS", "Ensure journald log file access is configured"),
        versi_cis=task_vars.get("VERSI_CIS", "Ubuntu 24.04 LTS Benchmark v2.0.0"),
        regulasi=task_vars.get("REGULASI", "Pasal 35, Pasal 36"),
        kepatuhan=task_vars.get("KEPATUHAN", "UU PDP No. 27/2022"),
        log_type="hardening",
    )

    lock_name = CATALOG_LOCKS.get("K09", "journald_audit")
    lock_file = acquire_lock(lock_name, logger)

    if lock_file is None:
        sys.exit(0)

    start = perf_counter()

    try:
        # Cek apakah Permission sudah dihardening
        is_compliant, message = check_journald_access(JOURNAL_LOG_DIR)

        if is_compliant:
            logger.log(
                LogStatus.SKIPPED,
                "Result",
                f"Hasil Hardening: SKIPPED - {message}",
                duration_ms=(perf_counter() - start) * 1000,
            )
            sys.exit(0)

        # Backup metadata sebelum melakukan perubahan.
        backup_success, backup_message = create_journald_access_backup()
        if not backup_success:
            logger.log(
                LogStatus.FAILED,
                "Result", 
                f"Hasil Hardening: BackupFailed - {backup_message}",
                duration_ms=(perf_counter() - start) * 1000, 
            )
            sys.exit(1)

        paths = [JOURNAL_LOG_DIR, *JOURNAL_LOG_DIR.rglob("*")]

        for path in paths:
            file_stat = path.lstat()

            if not (
                stat.S_ISDIR(file_stat.st_mode)
                or stat.S_ISREG(file_stat.st_mode)
            ):
                continue

            current_mode = stat.S_IMODE(file_stat.st_mode)

            if path == JOURNAL_LOG_DIR:
                new_mode = current_mode & ~stat.S_IWOTH
            else:
                new_mode = current_mode & ~(stat.S_IWGRP | stat.S_IWOTH)

            if new_mode != current_mode:
                path.chmod(new_mode)


        # Validasi ulang setelah hardening.
        is_compliant, validation_message = check_journald_access(
            JOURNAL_LOG_DIR
        )

        if not is_compliant:
            logger.log(
                LogStatus.FAILED,
                "Result",
                f"Hasil Hardening: FAILED - {validation_message}",
                duration_ms=(perf_counter() - start) * 1000,
            )
            sys.exit(1)
        
        logger.log(
            LogStatus.SUCCESS,
            "Result",
            f"Hasil Hardening: SUCCESS - Hardening permission journald berhasil diterapkan.",
            duration_ms=(perf_counter() - start) * 1000,
        )
        sys.exit(0)

    except Exception as e:
        logger.log_error(
            "K09", 
            "hardening", 
            e,
            duration_ms=(perf_counter() - start) * 1000,
        )
        sys.exit(2)
    finally:
        release_lock(lock_file)


if __name__ == "__main__":
    main()