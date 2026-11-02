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
    SYSCTL_TARGET_ICMP_ECHO_BROADCASTS,
    CATALOG_LOCKS,
)

from pipeline.catalogutils import (
    BaseLogger,
    acquire_lock,
    release_lock,
)


def apply_sysctl_hardening(sysctl_key: str, target_value: str, comment: str) -> tuple[bool, str]:
    """
    Menerapkan konfigurasi sysctl secara cerdas:
    - Jika file belum ada, buat baru.
    - Jika key sudah ada di file, update nilainya.
    - Jika key belum ada, append key tersebut ke file.
    """
    try:
        SYSCTL_CONF.parent.mkdir(parents=True, exist_ok=True)
        
        lines = []
        key_found = False

        # 1. Baca file yang sudah ada (jika ada)
        if SYSCTL_CONF.is_file():
            with open(SYSCTL_CONF, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line_stripped = line.strip()
                    # Cek apakah baris ini berisi key sysctl yang dimaksud (di luar komentar)
                    if not line_stripped.startswith("#") and "=" in line_stripped:
                        current_key = line_stripped.split("=")[0].strip()
                        if current_key == sysctl_key:
                            # Update nilai pada baris yang sama
                            lines.append(f"{sysctl_key} = {target_value}\n")
                            key_found = True
                            continue
                    lines.append(line)

        # 2. Tulis kembali atau buat file baru
        if not SYSCTL_CONF.is_file():
            content = f"# {comment}\n{sysctl_key} = {target_value}\n"
            SYSCTL_CONF.write_text(content, encoding="utf-8")
        elif not key_found:
            if lines and not lines[-1].endswith("\n"):
                lines.append("\n")
            lines.append(f"{sysctl_key} = {target_value}\n")
            with open(SYSCTL_CONF, "w", encoding="utf-8") as f:
                f.writelines(lines)
        else:
            with open(SYSCTL_CONF, "w", encoding="utf-8") as f:
                f.writelines(lines)

        # 3. Amankan izin akses file (0o644)
        os.chmod(SYSCTL_CONF, 0o644)

        # 4. Terapkan langsung via sysctl --system
        res = subprocess.run(
            ["sysctl", "--system"],
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode != 0:
            return False, f"Gagal menerapkan sysctl system: {res.stderr.strip()}"

        return True, f"Parameter {sysctl_key} = {target_value} berhasil diterapkan di {SYSCTL_CONF.name}."
    except Exception as e:
        return False, f"Gagal menerapkan hardening sysctl: {str(e)}"


def main():
    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="hardening.json",
        catalog="K16",
        cis_id="3.3.4",
        log_type="hardening",
    )

    lock_name = CATALOG_LOCKS.get("K16", "icmp_broadcast_audit")
    lock_file = acquire_lock(lock_name, logger)

    try:
        success, detail = apply_sysctl_hardening(
            sysctl_key=SYSCTL_KEY_ICMP_ECHO_BROADCASTS,
            target_value=SYSCTL_TARGET_ICMP_ECHO_BROADCASTS,
            comment="CIS 3.3.4: Ensure broadcast icmp requests are ignored",
        )

        if success:
            logger.log(
                "SUCCESS",
                "Result",
                f"Hasil Hardening: SUCCESS - {detail}",
            )
        else:
            logger.log(
                "FAILED",
                "Result",
                f"Hasil Hardening: FAILED - {detail}",
            )

    except Exception as e:
        logger.log_error("K16", "hardening", e)

    finally:
        release_lock(lock_file)


if __name__ == "__main__":
    main()