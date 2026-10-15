from __future__ import annotations
from pathlib import Path
import sys
import os
import tempfile
import shutil

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import JOURNALD_CONFIG, JOURNALD_BACKUP_DIR, CATALOG_LOCKS

from pipeline.catalogutils import (
    BaseLogger,
    acquire_lock,
    release_lock,
    check_journald_config_exists,
    create_journald_backup,
    restart_journald_service,
)


def check_storage_status(config_path: Path) -> bool:
    """Mengecek apakah Storage=persistent sudah aktif secara eksplisit."""
    if not config_path.is_file():
        return False
    with open(config_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            if line.strip().lower() == "storage=persistent":
                return True
    return False


def apply_storage_hardening(src_path: Path, dst_file_obj) -> None:
    """Memastikan Storage=persistent diatur pada journald.conf."""
    storage_found = False
    with open(src_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line_stripped = line.strip()
            if line_stripped.lower().startswith("storage=") or (
                (line_stripped.startswith("#") or line_stripped.startswith(";"))
                and "storage=" in line_stripped.lower()
            ):
                if not storage_found:
                    dst_file_obj.write("Storage=persistent\n")
                    storage_found = True
            else:
                dst_file_obj.write(line)
    
    if not storage_found:
        dst_file_obj.write("\nStorage=persistent\n")


def main():
    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="hardening.json",
        catalog="K15",
        cis_id="6.1.2.4",
        log_type="hardening",
    )

    lock_name = CATALOG_LOCKS.get("K15", "journald_storage")
    lock_file = acquire_lock(lock_name, logger)

    try:
        if not check_journald_config_exists(logger):
            logger.log(
                "FAILED", 
                "Result", 
                f"Hasil Hardening: FAILED - Berkas {JOURNALD_CONFIG} tidak ditemukan."
            )
            sys.exit(1)

        if check_storage_status(JOURNALD_CONFIG):
            logger.log(
                "SKIPPED", 
                "Result", 
                "Hasil Hardening: SKIPPED - Parameter Storage=persistent sudah aktif."
            )
            sys.exit(0)

        success_backup, backup_msg = create_journald_backup(JOURNALD_CONFIG, JOURNALD_BACKUP_DIR, logger)
        if not success_backup:
            logger.log(
                "FAILED", 
                "BackupFailed", 
                backup_msg
            )
            sys.exit(1)

        with tempfile.NamedTemporaryFile("w+", delete=False, prefix="journald_storage_") as tmp_file:
            tmp_config_path = Path(tmp_file.name)
            apply_storage_hardening(JOURNALD_CONFIG, tmp_file)

        shutil.move(str(tmp_config_path), str(JOURNALD_CONFIG))
        os.chmod(JOURNALD_CONFIG, 0o644)

        if restart_journald_service():
            logger.log(
                "SUCCESS", 
                "Result", 
                "Hasil Hardening: SUCCESS - Storage=persistent berhasil diterapkan."
            )
        else:
            logger.log(
                "WARNING", 
                "Result", 
                "Hasil Hardening: WARNING - Konfigurasi diubah tapi gagal restart service."
            )

    except Exception as e:
        logger.log_error("K15", "hardening", e)
        
    finally:
        release_lock(lock_file)


if __name__ == "__main__":
    main()