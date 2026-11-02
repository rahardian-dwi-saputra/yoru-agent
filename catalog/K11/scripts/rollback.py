from __future__ import annotations
from pathlib import Path
from datetime import datetime
from time import perf_counter
import base64
import json
import sys
import stat
import os
import tempfile

# Import modul catalogutils via sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]  # Naik 3 level ke yoru-agent/

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import (
    APP_TIMEZONE,
    JOURNALD_CONFIG,
    JOURNALD_BACKUP_DIR,
    JOURNALD_SERVICE_NAME,
    CATALOG_LOCKS,
)

from pipeline.catalogutils import (
    LogStatus,
    BaseLogger,
    load_taskfile_vars,
    acquire_lock,
    release_lock,
    restart_system_service,
)

BACKUP_FILE = JOURNALD_BACKUP_DIR / "journald-rotation.json"


def atomic_write(
    target: Path,
    content: bytes,
    mode: int = 0o600,
    uid: int | None = None,
    gid: int | None = None,
) -> None:
    """Menulis file secara atomik."""

    target.parent.mkdir(parents=True, exist_ok=True)
    temp_path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=target.parent,
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            temp_file.write(content)
            temp_file.flush()
            os.fsync(temp_file.fileno())

        os.replace(temp_path, target)

        if uid is not None and gid is not None:
            os.chown(target, uid, gid)

        os.chmod(target, mode)

    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()


def load_backup() -> dict:
    """Membaca dan memvalidasi file backup."""

    if BACKUP_FILE.is_symlink():
        raise RuntimeError("File backup tidak boleh berupa symbolic link.")

    if not BACKUP_FILE.is_file():
        raise FileNotFoundError(
            f"File backup tidak ditemukan: {BACKUP_FILE}"
        )

    try:
        with BACKUP_FILE.open("r", encoding="utf-8") as file:
            backup = json.load(file)
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"Gagal membaca file backup: {exc}") from exc

    if not isinstance(backup, dict):
        raise RuntimeError("Format backup tidak valid.")

    if backup.get("version") != 1:
        raise RuntimeError("Versi backup tidak didukung.")

    if backup.get("catalog") != "K11":
        raise RuntimeError("Backup bukan milik katalog K11.")

    if backup.get("config_file") != str(JOURNALD_CONFIG):
        raise RuntimeError("Target konfigurasi pada backup tidak sesuai.")

    if not isinstance(backup.get("exists"), bool):
        raise RuntimeError("Informasi keberadaan konfigurasi tidak valid.")

    if backup["exists"]:
        if not isinstance(backup.get("content"), str):
            raise RuntimeError("Konten konfigurasi pada backup tidak valid.")

        for key in ("mode", "uid", "gid"):
            value = backup.get(key)
            if type(value) is not int or value < 0:
                raise RuntimeError(f"Metadata backup {key} tidak valid.")

        try:
            backup["_content_bytes"] = base64.b64decode(
                backup["content"],
                validate=True,
            )
        except (ValueError, base64.binascii.Error) as exc:
            raise RuntimeError("Data konfigurasi backup tidak valid.") from exc

    return backup


def is_restored(backup: dict) -> bool:
    """Memeriksa apakah konfigurasi sudah kembali ke kondisi awal."""

    if JOURNALD_CONFIG.is_symlink():
        raise RuntimeError(
            "File konfigurasi berupa symbolic link. Rollback dibatalkan."
        )

    if not backup["exists"]:
        return not JOURNALD_CONFIG.exists()

    if not JOURNALD_CONFIG.is_file():
        return False

    file_stat = JOURNALD_CONFIG.stat()

    return (
        JOURNALD_CONFIG.read_bytes() == backup["_content_bytes"]
        and stat.S_IMODE(file_stat.st_mode) == backup["mode"]
        and file_stat.st_uid == backup["uid"]
        and file_stat.st_gid == backup["gid"]
    )


def restore_backup(backup: dict) -> None:
    """Memulihkan konfigurasi journald dari backup."""

    if JOURNALD_CONFIG.is_symlink():
        raise RuntimeError(
            "File konfigurasi berupa symbolic link. Rollback dibatalkan."
        )

    if backup["exists"]:
        atomic_write(
            target=JOURNALD_CONFIG,
            content=backup["_content_bytes"],
            mode=backup["mode"],
            uid=backup["uid"],
            gid=backup["gid"],
        )
    else:
        if JOURNALD_CONFIG.exists():
            if not JOURNALD_CONFIG.is_file():
                raise RuntimeError(
                    "Target konfigurasi bukan file biasa."
                )
            JOURNALD_CONFIG.unlink()


def main():
    task_vars = load_taskfile_vars(SCRIPT_DIR)

    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="rollback.json",
        catalog=task_vars.get("ID", "K11"),
        nama=task_vars.get("NAMA", "Konfigurasi Rotasi File Log Journald"),
        kode_cis=task_vars.get("KODE_CIS", "6.1.1.3"),
        judul_cis=task_vars.get("JUDUL_CIS", "Ensure journald log file rotation is configured"),
        versi_cis=task_vars.get("VERSI_CIS", "Ubuntu 24.04 LTS Benchmark v2.0.0"),
        regulasi=task_vars.get("REGULASI", "Pasal 31, Pasal 35"),
        kepatuhan=task_vars.get("KEPATUHAN", "UU PDP No. 27/2022"),
        log_type="rollback",
    )

    lock_name = CATALOG_LOCKS.get("K11", "journald_audit")
    lock_file = acquire_lock(lock_name, logger)

    start = perf_counter()

    try:
        backup = load_backup()

        if backup.get("rolled_back") is True:
            logger.log(
                LogStatus.SKIPPED,
                "Result",
                "Hasil Rollback: SKIPPED - konfigurasi sudah di-rollback sebelumnya.",
                duration_ms=(perf_counter() - start) * 1000,
            )
            sys.exit(0)

        # Periksa kondisi konfigurasi saat ini
        if is_restored(backup):
            backup["rolled_back"] = True
            backup["rollback_timestamp"] = datetime.now(APP_TIMEZONE).isoformat()

            backup.pop("_content_bytes", None)

            atomic_write(
                target=BACKUP_FILE,
                content=json.dumps(
                    backup,
                    indent=4,
                    ensure_ascii=False,
                ).encode("utf-8"),
                mode=0o600,
                uid=0,
                gid=0,
            )

            logger.log(
                LogStatus.SKIPPED,
                "Result",
                "Hasil Rollback: SKIPPED - konfigurasi sudah sesuai kondisi sebelum hardening.",
                duration_ms=(perf_counter() - start) * 1000,
            )
            return 0

        # Pulihkan konfigurasi
        restore_backup(backup)

        # Restart layanan journald
        if not restart_system_service(JOURNALD_SERVICE_NAME):
            raise RuntimeError(
                f"Gagal merestart layanan {JOURNALD_SERVICE_NAME}."
            )

        # Verifikasi hasil pemulihan
        if not is_restored(backup):
            raise RuntimeError(
                "Validasi rollback gagal: konfigurasi tidak sesuai backup."
            )

        # Tandai rollback berhasil
        backup["rolled_back"] = True
        backup["rollback_timestamp"] = datetime.now(APP_TIMEZONE).isoformat()

        backup.pop("_content_bytes", None)

        atomic_write(
            target=BACKUP_FILE,
            content=json.dumps(
                backup,
                indent=4,
                ensure_ascii=False,
            ).encode("utf-8"),
            mode=0o600,
            uid=0,
            gid=0,
        )

        logger.log(
            LogStatus.SUCCESS,
            "Result",
            "Hasil Rollback: SUCCESS - Konfigurasi journald berhasil dikembalikan ke kondisi sebelum hardening.",
            duration_ms=(perf_counter() - start) * 1000,
        )
        sys.exit(0)

    except Exception as e:
        logger.log_error(
            "K11", 
            "rollback", 
            e, 
            duration_ms=(perf_counter() - start) * 1000,
        )
        sys.exit(2)

    finally:
        release_lock(lock_file)


if __name__ == "__main__":
    main()