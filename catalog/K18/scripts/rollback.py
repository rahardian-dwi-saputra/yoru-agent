from __future__ import annotations
from pathlib import Path
import subprocess
import sys
import os

# Import modul catalogutils via sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]  # Naik 3 level ke yoru-agent/

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import (
    SYSCTL_CONF,
    SYSCTL_KEYS_ACCEPT_SOURCE_ROUTE,
    SYSCTL_DEFAULT_ACCEPT_SOURCE_ROUTE,
    CATALOG_LOCKS,
)

from pipeline.catalogutils import (
    BaseLogger,
    acquire_lock,
    release_lock,
)


def perform_sysctl_rollback_list(sysctl_keys: list[str]) -> tuple[str, str]:
    """
    Melakukan rollback sysctl untuk daftar kunci (list of keys) secara cerdas:
    - Jika file conf tidak ditemukan -> CANCELLED
    - Jika seluruh kunci tidak ditemukan di file -> CANCELLED
    - Jika semua kunci sudah bernilai default (0) -> SKIPPED
    - Jika ada kunci yang ditemukan dengan nilai lain -> SUCCESS (ubah ke 0)
    """
    try:
        if not SYSCTL_CONF.is_file():
            return "CANCELLED", f"Berkas konfigurasi {SYSCTL_CONF.name} tidak ditemukan."

        existing_lines = []
        with open(SYSCTL_CONF, "r", encoding="utf-8", errors="ignore") as f:
            existing_lines = f.readlines()

        keys_found_count = 0
        all_already_default = True
        new_lines = []

        # 1. Periksa dan ubah nilai kunci yang terdaftar
        for line in existing_lines:
            line_stripped = line.strip()
            handled = False
            if not line_stripped.startswith("#") and "=" in line_stripped:
                parts = [x.strip() for x in line_stripped.split("=", 1)]

                if len(parts) == 2:
                    current_key = parts[0].strip()
                    current_val = parts[1].strip()
                    
                    for target_key in sysctl_keys:
                        if current_key == target_key:
                            keys_found_count += 1
                            if current_val != SYSCTL_DEFAULT_ACCEPT_SOURCE_ROUTE:
                                all_already_default = False
                                new_lines.append(f"{target_key} = {SYSCTL_DEFAULT_ACCEPT_SOURCE_ROUTE}\n")
                            else:
                                new_lines.append(line)  # Sudah bernilai default, pertahankan
                            handled = True
                            break
            if not handled:
                new_lines.append(line)

        # 2. Validasi aturan status
        if keys_found_count == 0:
            keys_str = ", ".join(sysctl_keys)
            return "CANCELLED", f"Tidak ada satupun parameter dari [{keys_str}] yang ditemukan di dalam {SYSCTL_CONF.name}."

        if all_already_default:
            return "SKIPPED", "Seluruh parameter accept_redirects sudah bernilai default (1)."

        # 3. Tulis ulang file konfigurasi hasil rollback
        with open(SYSCTL_CONF, "w", encoding="utf-8") as f:
            f.writelines(new_lines)

        # 4. Amankan izin akses file (0o644)
        os.chmod(SYSCTL_CONF, 0o644)

        # 5. Terapkan langsung via sysctl --system
        res = subprocess.run(
            ["sysctl", "--system"],
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode != 0:
            return "FAILED", f"Gagal menerapkan sysctl system saat rollback: {res.stderr.strip()}"

        keys_str = ", ".join(sysctl_keys)
        return "SUCCESS", f"Parameter [{keys_str}] berhasil di-rollback ke nilai {SYSCTL_DEFAULT_ACCEPT_SOURCE_ROUTE}."

    except Exception as e:
        return "FAILED", f"Gagal melakukan rollback sysctl: {str(e)}"


def main():
    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="rollback.json",
        catalog="K18",
        cis_id="3.3.8",
        log_type="rollback",
    )

    lock_name = CATALOG_LOCKS.get("K18", "source_route_rollback")
    lock_file = acquire_lock(lock_name, logger)

    try:
        status, detail = perform_sysctl_rollback_list(SYSCTL_KEYS_ACCEPT_SOURCE_ROUTE)

        if status == "SUCCESS":
            logger.log(
                "SUCCESS", 
                "Result", 
                f"Hasil Rollback: SUCCESS - {detail}"
            )
        elif status == "SKIPPED":
            logger.log(
                "SKIPPED", 
                "Result", 
                f"Hasil Rollback: SKIPPED - {detail}"
            )
        elif status == "CANCELLED":
            logger.log(
                "CANCELLED", 
                "Result", 
                f"Hasil Rollback: CANCELLED - {detail}"
            )
        else:
            logger.log(
                "FAILED", 
                "Result", 
                f"Hasil Rollback: FAILED - {detail}"
            )

    except Exception as e:
        logger.log_error("K18", "rollback", e)

    finally:
        release_lock(lock_file)


if __name__ == "__main__":
    main()