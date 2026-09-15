from __future__ import annotations
from pathlib import Path
import sys

# Import modul catalogutils via sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]  # Naik 3 level ke yoru-agent/

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.catalogutils import (
    SSHD_CONFIG,
    BaseLogger,
    acquire_lock,
    get_non_root_users,
    check_sshd_config_exists,
    release_lock,
)

def check_permit_root_login() -> str:
    """Mengecek konfigurasi PermitRootLogin di sshd_config."""
    if not SSHD_CONFIG.is_file():
        return "not_found"

    with open(SSHD_CONFIG, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line_stripped = line.strip()
            if line_stripped.startswith("#"):
                continue

            if line_stripped.lower().startswith("permitrootlogin"):
                parts = line_stripped.split()
                if len(parts) >= 2:
                    return parts[1]
    return "not_set"

def main():
    
    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="audit.json",
        catalog="K01",
        cis_id="5.1.20",
        log_type="audit",
    )

    # Kunci eksekusi skrip
    lock_file = acquire_lock(logger)

    logger.log(
        "INFO", 
        "Start", 
        "Memulai audit CIS 5.1.20 (sshd PermitRootLogin)..."
    )
    audit_passed = True

    try:
        if not check_sshd_config_exists(logger):
            logger.log(
                "FAILED", 
                "Result", 
                "Hasil Audit: FAILED - File sshd_config tidak ditemukan."
            )
            sys.exit(1)

        users = get_non_root_users()
        if not users:
            logger.log(
                "WARNING",
                "Note",
                "Tidak ditemukan user lain yang memiliki akses login SSH.",
            )
            audit_passed = False
        else:
            logger.log(
                "INFO",
                "Note",
                f"Ditemukan {len(users)} user non-root aktif: {', '.join(users)}",
            )

        status = check_permit_root_login()
        if status == "not_set":
            logger.log(
                "WARNING",
                "Note",
                "PermitRootLogin tidak diatur secara eksplisit di sshd_config",
            )
            audit_passed = False
        elif status.lower() == "yes":
            logger.log(
                "WARNING",
                "Note",
                "Root BISA login via SSH (PermitRootLogin yes)"
            )
            audit_passed = False
        else:
            logger.log(
                "INFO",
                "Note",
                f"Root login SSH AMAN / Dibatasi (Status: {status})"
            )

        if audit_passed:
            logger.log(
                "PASSED",
                "Result",
                "Hasil Audit: PASSED - Konfigurasi PermitRootLogin sudah sesuai standar CIS.",
            )
        else:
            logger.log(
                "FAIL",
                "Result",
                "Hasil Audit: FAILED - Konfigurasi PermitRootLogin tidak memenuhi standar CIS.",
            )

    except Exception as e:
        logger.log_error("K01", "audit", e)
        
    finally:
        # Melepaskan penguncian file
        release_lock(lock_file)


if __name__ == "__main__":
    main()