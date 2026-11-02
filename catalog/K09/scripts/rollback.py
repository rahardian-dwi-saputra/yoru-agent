from __future__ import annotations
from pathlib import Path
from time import perf_counter
import os
import stat
import sys
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
)


def main():
    task_vars = load_taskfile_vars(SCRIPT_DIR)

    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="rollback.json",
        catalog=task_vars.get("ID", "K09"),
        nama=task_vars.get("NAMA", "Pengaturan Akses File Log Journald"),
        kode_cis=task_vars.get("KODE_CIS", "6.1.1.2"),
        judul_cis=task_vars.get("JUDUL_CIS", "Ensure journald log file access is configured"),
        versi_cis=task_vars.get("VERSI_CIS", "Ubuntu 24.04 LTS Benchmark v2.0.0"),
        regulasi=task_vars.get("REGULASI", "Pasal 35, Pasal 36"),
        kepatuhan=task_vars.get("KEPATUHAN", "UU PDP No. 27/2022"),
        log_type="rollback",
    )

    lock_name = CATALOG_LOCKS.get("K09", "journald_audit")
    lock_file = acquire_lock(lock_name, logger)

    if lock_file is None:
        sys.exit(0)
    
    start = perf_counter()

    try:
        if not JOURNAL_ACCESS_BACKUP.is_file():
            logger.log(
                LogStatus.FAILED,
                "Result",
                f"Hasil Rollback: FAILED - Backup metadata tidak ditemukan: {JOURNAL_ACCESS_BACKUP}",
                duration_ms=(perf_counter() - start) * 1000,
            )
            sys.exit(1)

        # Pastikan direktori log merupakan direktori asli.
        if not stat.S_ISDIR(JOURNAL_LOG_DIR.lstat().st_mode):
            logger.log(
                LogStatus.FAILED,
                "Result",
                "Hasil Rollback: FAILED - Direktori log journald tidak valid.",
                duration_ms=(perf_counter() - start) * 1000,
            )
            sys.exit(1)

        # Baca backup metadata.
        with JOURNAL_ACCESS_BACKUP.open("r", encoding="utf-8") as file:
            backup_data = json.load(file)

        if (
            backup_data.get("version") != 1
            or backup_data.get("root") != str(JOURNAL_LOG_DIR)
            or not isinstance(backup_data.get("entries"), list)
        ):
            logger.log(
                LogStatus.FAILED,
                "Result",
                "Hasil Rollback: FAILED - Format atau identitas backup metadata tidak valid.",
                duration_ms=(perf_counter() - start) * 1000,
            )
            sys.exit(1)

        entries = backup_data["entries"]

        if not entries:
            logger.log(
                LogStatus.FAILED,
                "Result",
                "Hasil Rollback: FAILED - Backup metadata tidak memiliki data untuk dipulihkan.",
                duration_ms=(perf_counter() - start) * 1000,
            )
            sys.exit(1)

        restore_items = []
        restored_paths = set()

        # Validasi seluruh metadata dan objek sebelum pemulihan.
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError("Format entry backup tidak valid.")
               
            relative_path = Path(entry["path"])

            if (
                relative_path.is_absolute()
                or ".." in relative_path.parts
                or relative_path == Path("")
            ):
                raise ValueError("Backup mengandung path yang tidak valid.")

            if relative_path in restored_paths:
                raise ValueError(f"Path duplikat dalam backup: {relative_path}")

            restored_paths.add(relative_path)

            object_type = entry["type"]

            if object_type not in ("file", "directory"):
                raise ValueError(f"Tipe objek tidak valid: {relative_path}")

            mode = entry["mode"]
            uid = entry["uid"]
            gid = entry["gid"]

            if (
                not isinstance(mode, int)
                or isinstance(mode, bool)
                or not 0 <= mode <= 0o7777
                or not isinstance(uid, int)
                or isinstance(uid, bool)
                or uid < 0
                or not isinstance(gid, int)
                or isinstance(gid, bool)
                or gid < 0
            ):
                raise ValueError(
                    f"Metadata permission atau ownership tidak valid: "
                    f"{relative_path}"
                )

            path = JOURNAL_LOG_DIR / relative_path

            # Pastikan seluruh parent merupakan direktori asli, bukan symlink.
            parent = JOURNAL_LOG_DIR

            for part in relative_path.parts[:-1]:
                parent = parent / part
                parent_stat = parent.lstat()

                if not stat.S_ISDIR(parent_stat.st_mode):
                    raise ValueError(f"Direktori induk tidak valid: {parent}")

            current_stat = path.lstat()

            expected_type = (
                stat.S_ISDIR(current_stat.st_mode)
                if object_type == "directory"
                else stat.S_ISREG(current_stat.st_mode)
            )

            if not expected_type:
                raise ValueError(f"Tipe objek tidak sesuai dengan backup: {path}")

            restore_items.append({
                "path": path,
                "mode": mode,
                "uid": uid,
                "gid": gid,
                "type": object_type,
            })
    
        
        # Pastikan direktori utama tercatat dalam backup.
        root_entries = [
            item for item in restore_items
            if item["path"] == JOURNAL_LOG_DIR
            and item["type"] == "directory"
        ]

        if not root_entries:
            raise ValueError("Backup tidak memiliki metadata direktori utama journald.")

        # Pulihkan ownership terlebih dahulu.
        for item in restore_items:
            os.chown(
                item["path"],
                item["uid"],
                item["gid"],
                follow_symlinks=False,
            )

        # Pulihkan permission file terlebih dahulu.
        files = [
            item for item in restore_items
            if item["type"] == "file"
        ]

        # Pulihkan direktori dari terdalam ke terluar.
        directories = sorted(
            (
                item for item in restore_items
                if item["type"] == "directory"
            ),
            key=lambda item: len(item["path"].parts),
            reverse=True,
        )

        for item in [*files, *directories]:
            item["path"].chmod(item["mode"])

        # Hapus backup hanya setelah seluruh proses berhasil.
        JOURNAL_ACCESS_BACKUP.unlink()

        logger.log(
            LogStatus.SUCCESS,
            "Result",
            f"Hasil Rollback: SUCCEED - Permission dan ownership direktori serta file log journald berhasil dikembalikan sesuai kondisi sebelum hardening.",
            duration_ms=(perf_counter() - start) * 1000,
        )
        sys.exit(0)

    except Exception as e:
        logger.log_error(
            "K09", 
            "rollback", 
            e,
            duration_ms=(perf_counter() - start) * 1000,
        )
        sys.exit(2)
    finally:
        release_lock(lock_file)


if __name__ == "__main__":
    main()