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
    SYSCTL_KEY_ICMP_ECHO_BROADCASTS,
    SYSCTL_DEFAULT_ICMP_ECHO_BROADCASTS,
    CATALOG_LOCKS,
)

from pipeline.catalogutils import (
    BaseLogger,
    acquire_lock,
    release_lock,
)


def perform_sysctl_rollback(sysctl_key: str) -> tuple[str, str]:
    """
    Melakukan rollback sysctl secara cerdas:
    - Jika file conf atau parameter tidak ditemukan -> CANCELLED
    - Jika nilai parameter sudah 0 -> SKIPPED
    - Jika parameter ditemukan dengan nilai lain -> SUCCESS (ubah ke 0)
    """
    try:
        if not SYSCTL_CONF.is_file():
            return "CANCELLED", f"Berkas konfigurasi {SYSCTL_CONF.name} tidak ditemukan."

        lines = []
        key_found = False
        current_value = None

       
        with open(SYSCTL_CONF, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line_stripped = line.strip()
                if not line_stripped.startswith("#") and "=" in line_stripped:
                    key, val = [x.strip() for x in line_stripped.split("=", 1)]
                    if key == sysctl_key:
                        key_found = True
                        current_value = val
                        if val == SYSCTL_DEFAULT_ICMP_ECHO_BROADCASTS:
                            return "SKIPPED", f"Parameter {sysctl_key} sudah bernilai default ({SYSCTL_DEFAULT_ICMP_ECHO_BROADCASTS})."
                        else:
                            lines.append(f"{sysctl_key} = {SYSCTL_DEFAULT_ICMP_ECHO_BROADCASTS}\n")
                            continue
                lines.append(line)

        if not key_found:
            return "CANCELLED", f"Parameter {sysctl_key} tidak ditemukan di dalam {SYSCTL_CONF.name}."

        # Tulis kembali file dengan nilai yang sudah di-rollback
        with open(SYSCTL_CONF, "w", encoding="utf-8") as f:
            f.writelines(lines)

        # Amankan izin akses file (0o644)
        os.chmod(SYSCTL_CONF, 0o644)

        # Terapkan langsung via sysctl --system
        res = subprocess.run(
            ["sysctl", "--system"],
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode != 0:
            return "FAILED", f"Gagal menerapkan sysctl system saat rollback: {res.stderr.strip()}"

        return "SUCCESS", f"Parameter {sysctl_key} berhasil di-rollback ke nilai {SYSCTL_DEFAULT_ICMP_ECHO_BROADCASTS}."

    except Exception as e:
        return "FAILED", f"Gagal melakukan rollback sysctl: {str(e)}"


def main():
    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="rollback.json",
        catalog="K16",
        cis_id="3.3.4",
        log_type="rollback",
    )

    lock_name = CATALOG_LOCKS.get("K16", "icmp_broadcast_audit")
    lock_file = acquire_lock(lock_name, logger)

    try:
        status, detail = perform_sysctl_rollback(SYSCTL_KEY_ICMP_ECHO_BROADCASTS)

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
        logger.log_error("K16", "rollback", e)

    finally:
        release_lock(lock_file)


if __name__ == "__main__":
    main()