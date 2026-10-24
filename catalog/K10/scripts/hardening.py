from __future__ import annotations
from pathlib import Path
import subprocess
import sys
import os
import tempfile
import shutil

# Import modul catalogutils via sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]  # Naik 3 level ke yoru-agent/

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import JOURNALD_CONFIG, TARGET_SYSTEM_MAX_USE, CATALOG_LOCKS

from pipeline.catalogutils import (
    BaseLogger,
    acquire_lock,
    release_lock,
    check_journald_config_exists,
    create_journald_backup,
    check_journald_disk_space_prerequisite,
    restart_journald_service,
)


def check_journald_hardening_status(config_path: Path) -> bool:
    """Mengecek apakah Storage=persistent, SystemMaxUse, dan MaxRetentionSec sudah terpasang."""
    if not config_path.is_file():
        return False
    
    found_persistent = False
    found_max_use = False
    found_retention = False

    with open(config_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line_str = line.strip().lower()
            if line_str.startswith("storage=persistent"):
                found_persistent = True
            elif line_str.startswith("systemmaxuse="):
                found_max_use = True
            elif line_str.startswith("maxretentionsec="):
                found_retention = True

    return found_persistent and found_max_use and found_retention


def apply_journald_hardening(src_path: Path, dst_file_obj) -> None:
    """Menulis atau memperbarui parameter journald secara eksplisit."""
    
    params_to_set = {
        "Storage": "persistent",
        "Compress": "yes",
        "SystemMaxUse": TARGET_SYSTEM_MAX_USE,
        "MaxRetentionSec": "1month"
    }
    
    seen_keys = set()

    with open(src_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line_stripped = line.strip()
            written = False
            
            if not line_stripped.startswith("#") and not line_stripped.startswith(";") and "=" in line_stripped:
                key = line_stripped.split("=")[0].strip()
                for target_key in params_to_set:
                    if key.lower() == target_key.lower():
                        dst_file_obj.write(f"{target_key}={params_to_set[target_key]}\n")
                        seen_keys.add(target_key)
                        written = True
                        break
            
            if not written:
                dst_file_obj.write(line)

    # Tambahkan parameter yang belum ada di file
    for target_key, val in params_to_set.items():
        if target_key not in seen_keys:
            dst_file_obj.write(f"{target_key}={val}\n")


def main():
    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="hardening.json",
        catalog="K14",
        cis_id="6.1.2.3",
        log_type="hardening",
    )

    lock_name = CATALOG_LOCKS.get("K14", "journald_audit")
    lock_file = acquire_lock(lock_name, logger)

    try:
        if not check_journald_config_exists(logger):
            logger.log(
                "FAILED", 
                "Result", 
                f"Hasil Hardening: FAILED - Berkas konfigurasi {JOURNALD_CONFIG} tidak ditemukan."
            )
            sys.exit(1)

        # 1. Jalankan Pre-Flight Check: Validasi Kapasitas Disk (Minimal 3x SystemMaxUse)
        if not check_journald_disk_space_prerequisite(TARGET_SYSTEM_MAX_USE, logger):
            logger.log(
                "FAILED", 
                "Result", 
                "Hasil Hardening: FAILED - Kapasitas disk /var/log tidak memenuhi prasyarat minimal 3x SystemMaxUse."
            )
            sys.exit(1)

        # 2. Cek apakah sudah memenuhi seluruh prasyarat parameter secara eksplisit
        if check_journald_hardening_status(JOURNALD_CONFIG):
            logger.log(
                "SKIPPED", 
                "Result", 
                "Hasil Hardening: SKIPPED - Parameter journald sudah ter-hardening secara lengkap."
            )
            sys.exit(0)

        # 3. Buat Backup Berversi
        success_backup, backup_msg = create_journald_backup(logger)
        if not success_backup:
            logger.log(
                "FAILED", 
                "BackupFailed", 
                backup_msg
            )
            sys.exit(1)

        # 4. Terapkan Modifikasi via Tempfile (Atomic Write)
        with tempfile.NamedTemporaryFile("w+", delete=False, prefix="journald_conf_") as tmp_file:
            tmp_config_path = Path(tmp_file.name)
            apply_journald_hardening(JOURNALD_CONFIG, tmp_file)

        shutil.move(str(tmp_config_path), str(JOURNALD_CONFIG))
        os.chmod(JOURNALD_CONFIG, 0o644)

        # 5. Restart Service Journald
        if restart_journald_service():
            logger.log(
                "SUCCESS", 
                "Result", 
                "Hasil Hardening: SUCCESS - Konfigurasi journald berhasil diperbarui dan service di-restart."
            )
        else:
            logger.log(
                "WARNING", 
                "Result", 
                "Hasil Hardening: WARNING - Konfigurasi diperbarui tetapi gagal merestart service systemd-journald."
            )

    except Exception as e:
        logger.log_error("K14", "hardening", e)

    finally:
        release_lock(lock_file)


if __name__ == "__main__":
    main()