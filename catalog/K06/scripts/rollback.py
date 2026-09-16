from __future__ import annotations
from pathlib import Path
from typing import List, Optional, Tuple
import os
import shutil
import subprocess
import sys
import tempfile


# Import modul catalogutils via sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]  # Naik 3 level ke yoru-agent/

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.catalogutils import (
    SSHD_CONFIG,
    BaseLogger,
    acquire_lock,
    check_sshd_config_exists,
    release_lock,
    restart_ssh_service,
)

# Daftar MACs hasil hardening K06
HARDENED_MACS_LIST = [
    "hmac-sha2-512-etm@openssh.com",
    "hmac-sha2-256-etm@openssh.com",
    "umac-128-etm@openssh.com",
    "hmac-sha2-512",
    "hmac-sha2-256",
    "umac-128@openssh.com",
]
HARDENED_MACS_SET = set(HARDENED_MACS_LIST)


def parse_macs_from_config(config_path: Path) -> Tuple[str, Optional[List[str]]]:
    """Mengecek dan meng-extract daftar MACs dari file sshd_config."""
    if not config_path.is_file():
        return "not_found", None

    with open(config_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line_stripped = line.strip()

            if line_stripped.startswith("#"):
                uncommented = line_stripped[1:].lstrip()
                if uncommented.lower().startswith("macs"):
                    parts = uncommented.split(maxsplit=1)
                    if len(parts) >= 2:
                        raw_macs = parts[1].strip()
                        return "commented", [m.strip() for m in raw_macs.split(",")]

            elif line_stripped.lower().startswith("macs"):
                parts = line_stripped.split(maxsplit=1)
                if len(parts) >= 2:
                    raw_macs = parts[1].strip()
                    return "active", [m.strip() for m in raw_macs.split(",")]

    return "not_found", None


def apply_rollback_macs(src_path: Path, dst_file_obj) -> None:
    """Mengomentari atau mengembalikan baris MACs ke kondisi default/terkomentar."""
    with open(src_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line_stripped = line.strip()

            # Jika baris merupakan direktif MACs aktif, ubah menjadi terkomentar
            if not line_stripped.startswith("#") and line_stripped.lower().startswith("macs"):
                dst_file_obj.write(f"# {line_stripped}\n")
            else:
                dst_file_obj.write(line)


def main():
    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="rollback.json",
        catalog="K06",
        cis_id="5.1.7",
        log_type="rollback",
    )

    lock_file = acquire_lock(logger)

    try:
        if not check_sshd_config_exists(logger):
            logger.log(
                "FAILED",
                "Result",
                "Hasil Rollback: FAILED - File sshd_config tidak ditemukan.",
            )
            sys.exit(1)

        # Cek status MACs saat ini
        state, current_macs = parse_macs_from_config(SSHD_CONFIG)

        # Syarat 1: Parameter tidak ditemukan -> Batalkan rollback
        if state == "not_found":
            logger.log(
                "FAILED",
                "Result",
                "Hasil Rollback: CANCELLED - Parameter MACs tidak ditemukan di sshd_config.",
            )
            sys.exit(0)

        # Syarat 2: Parameter terkomentar (#) -> Batalkan rollback
        if state == "commented":
            logger.log(
                "FAILED",
                "Result",
                "Hasil Rollback: CANCELLED - Parameter MACs sudah dalam keadaan terkomentar (#).",
            )
            sys.exit(0)

        # Syarat 3: Jika nilainya bukan nilai hasil hardening K06 -> Batalkan rollback
        if state == "active" and current_macs:
            current_set = set(current_macs)
            if current_set != HARDENED_MACS_SET:
                logger.log(
                    "SKIPPED",
                    "Result",
                    "Hasil Rollback: SKIPPED - Konfigurasi MACs aktif saat ini bukan berasal dari hasil hardening K06.",
                )
                sys.exit(0)

        # 3. Jalankan proses rollback (mengomentari direktif MACs)
        with tempfile.NamedTemporaryFile(
            "w+", delete=False, prefix="sshd_config_"
        ) as tmp_file:
            tmp_config_path = Path(tmp_file.name)
            apply_rollback_macs(SSHD_CONFIG, tmp_file)

        # 4. Validasi sintaks sshd
        validate_cmd = subprocess.run(
            ["sshd", "-t", "-f", str(tmp_config_path)], capture_output=True
        )

        if validate_cmd.returncode == 0:
            shutil.move(str(tmp_config_path), str(SSHD_CONFIG))
            os.chmod(SSHD_CONFIG, 0o600)

            if restart_ssh_service():
                logger.log(
                    "SUCCESS",
                    "Result",
                    "Hasil Rollback: SUCCEED - Konfigurasi MACs berhasil dikembalikan ke kondisi default sistem.",
                )
            else:
                logger.log(
                    "WARNING",
                    "Result",
                    "Hasil Rollback: WARNING - Konfigurasi MACs dikembalikan ke default, tetapi gagal merestart service SSH.",
                )
        else:
            if tmp_config_path.exists():
                tmp_config_path.unlink()
            logger.log(
                "FAILED",
                "Result",
                "Hasil Rollback: CANCELLED - Sintaks konfigurasi invalid! Rollback dibatalkan.",
            )
            sys.exit(1)

    except Exception as e:
        logger.log_error("K06", "rollback", e)

    finally:
        release_lock(lock_file)


if __name__ == "__main__":
    main()