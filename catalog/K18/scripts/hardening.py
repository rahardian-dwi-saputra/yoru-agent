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
    SYSCTL_TARGET_ACCEPT_SOURCE_ROUTE,
    CATALOG_LOCKS,
)

from pipeline.catalogutils import (
    BaseLogger,
    acquire_lock,
    release_lock,
)


SYSCTL_CONTENT = """# CIS 3.3.8: Ensure source routed packets are not accepted
net.ipv4.conf.all.accept_source_route = 0
net.ipv4.conf.default.accept_source_route = 0
"""


def apply_sysctl_hardening_list(sysctl_keys: list[str], target_value: str, comment: str) -> tuple[bool, str]:
    """
    Menerapkan konfigurasi sysctl untuk daftar kunci (list of keys) secara cerdas:
    - Jika file belum ada, buat baru.
    - Untuk setiap kunci dalam list: jika kunci sudah ada, update nilainya; jika belum, append ke file.
    """
    try:
        SYSCTL_CONF.parent.mkdir(parents=True, exist_ok=True)
        
        # 1. Baca seluruh baris file yang sudah ada (jika ada)
        existing_lines = []
        if SYSCTL_CONF.is_file():
            with open(SYSCTL_CONF, "r", encoding="utf-8", errors="ignore") as f:
                existing_lines = f.readlines()

        # 2. Proses pembaruan atau penambahan untuk setiap key dalam target list
        processed_keys = set()
        new_lines = []

        # Jika file belum ada sama sekali, buat dengan header komentar awal
        if not SYSCTL_CONF.is_file():
            new_lines.append(f"# {comment}\n")
            for key in sysctl_keys:
                new_lines.append(f"{key} = {target_value}\n")
                processed_keys.add(key)
        else:
            # Periksa baris demi baris untuk meng-update key yang sudah ada
            for line in existing_lines:
                line_stripped = line.strip()
                updated = False
                if not line_stripped.startswith("#") and "=" in line_stripped:
                    current_key = line_stripped.split("=")[0].strip()
                    for key in sysctl_keys:
                        if current_key == key:
                            new_lines.append(f"{key} = {target_value}\n")
                            processed_keys.add(key)
                            updated = True
                            break
                if not updated:
                    new_lines.append(line)

            # Tambahkan key yang belum ada sama sekali di dalam file
            for key in sysctl_keys:
                if key not in processed_keys:
                    if new_lines and not new_lines[-1].endswith("\n"):
                        new_lines.append("\n")
                    new_lines.append(f"{key} = {target_value}\n")

        # 3. Tulis ulang file konfigurasi
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
            return False, f"Gagal menerapkan sysctl system: {res.stderr.strip()}"

        keys_str = ", ".join(sysctl_keys)
        return True, f"Parameter [{keys_str}] = {target_value} berhasil diterapkan di {SYSCTL_CONF.name}."
    except Exception as e:
        return False, f"Gagal menerapkan hardening sysctl: {str(e)}"


def main():
    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="hardening.json",
        catalog="K18",
        cis_id="3.3.8",
        log_type="hardening",
    )

    lock_name = CATALOG_LOCKS.get("K18", "source_route_hardening")
    lock_file = acquire_lock(lock_name, logger)

    try:
        success, detail = apply_sysctl_hardening_list(
            sysctl_keys=SYSCTL_KEYS_ACCEPT_SOURCE_ROUTE,
            target_value=SYSCTL_TARGET_ACCEPT_SOURCE_ROUTE,
            comment="CIS 3.3.8 Ensure source routed packets are not accepted",
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
        logger.log_error("K18", "hardening", e)

    finally:
        release_lock(lock_file)


if __name__ == "__main__":
    main()