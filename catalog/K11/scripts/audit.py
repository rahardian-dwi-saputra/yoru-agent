from __future__ import annotations
from pathlib import Path
import sys
import subprocess


# Import modul catalogutils via sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]  # Naik 3 level ke yoru-agent/

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import (
    UFW_PACKAGE_NAME, 
    CATALOG_LOCKS
)

from pipeline.catalogutils import (
    BaseLogger,
    acquire_lock,
    release_lock,
    is_package_installed
)


def check_ufw_rules_exist() -> tuple[bool, str]:
    """
    Mengecek apakah UFW memiliki aturan (rules) kustom yang aktif.
    Sesuai CIS 3.5.1: Ensure firewall rules exist.
    """
    try:
        result = subprocess.run(
            ["ufw", "status", "verbose"],
            capture_output=True,
            text=True,
            check=False
        )
        
        if result.returncode != 0:
            return False, "Gagal mengeksekusi perintah ufw status."

        output = result.stdout.lower()
        
        if "status: inactive" in output:
            return False, "Layanan UFW dalam status inactive."

        # Analisis baris output untuk mendeteksi apakah ada aturan kustom
        lines = [line.strip() for line in output.splitlines() if line.strip()]
        
        # Jika baris hanya berisi header dasar (misal: Status: active, Default: deny, dll), 
        # artinya belum ada aturan port/traffic kustom yang dibuat.
        # Biasanya output standar UFW aktif tanpa aturan memiliki sekitar 4-5 baris header.
        rule_count = 0
        is_reading_rules = False
        
        for line in lines:
            if "-- trad" in line or "to" in line and "action" in line:  # Header tabel UFW
                is_reading_rules = True
                continue
            if is_reading_rules and line and not line.startswith("---"):
                rule_count += 1

        # Jika ditemukan baris aturan di luar default policy
        if rule_count > 0 or any("allow" in l or "deny" in l for l in lines[3:]):
            return True, f"Ditemukan aturan firewall aktif ({rule_count} aturan terdeteksi)."
            
        return False, "UFW aktif, tetapi belum ada aturan firewall kustom yang dikonfigurasi."
        
    except Exception as e:
        return False, f"Error saat memeriksa aturan ufw: {str(e)}"


def main():
    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="audit.json",
        catalog="K11",
        cis_id="3.5.1",
        log_type="audit",
    )

    lock_name = CATALOG_LOCKS.get("K11", "ufw_audit")
    lock_file = acquire_lock(lock_name, logger)

    try:
        if not is_package_installed(UFW_PACKAGE_NAME):
            logger.log(
                "FAILED",
                "Result",
                f"Hasil Audit: FAILED - Paket '{UFW_PACKAGE_NAME}' belum terinstall pada sistem.",
            )
            sys.exit(1)

    
        has_rules, message = check_ufw_rules_exist()

        if has_rules:
            logger.log(
                "COMPLIANT",
                "Result",
                f"Hasil Audit: COMPLIANT - {message}",
            )
        else:
            logger.log(
                "NON_COMPLIANT",
                "Result",
                f"Hasil Audit: NON_COMPLIANT - {message}",
            )
            
    except Exception as e:
        logger.log_error("K11", "audit", e)

    finally:
        release_lock(lock_file)


if __name__ == "__main__":
    main()