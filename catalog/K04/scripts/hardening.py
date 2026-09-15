from __future__ import annotations
from pathlib import Path
from typing import Optional, Tuple
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


def parse_max_auth_tries(raw_value: str) -> Optional[int]:
    """Mengonversi nilai MaxAuthTries ke tipe data integer."""
    try:
        return int(raw_value.strip())
    except ValueError:
        return None


def get_current_max_auth_tries(
    config_path: Path,
) -> Tuple[str, Optional[str], Optional[int]]:
    """Mengecek status dan nilai MaxAuthTries saat ini di sshd_config."""
    if not config_path.is_file():
        return "not_found", None, None

    with open(config_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line_stripped = line.strip()

            if line_stripped.startswith("#"):
                uncommented = line_stripped[1:].lstrip()
                if uncommented.lower().startswith("maxauthtries"):
                    parts = uncommented.split()
                    raw_val = parts[1] if len(parts) >= 2 else None
                    tries = parse_max_auth_tries(raw_val) if raw_val else None
                    return "commented", raw_val, tries

            elif line_stripped.lower().startswith("maxauthtries"):
                parts = line_stripped.split()
                raw_val = parts[1] if len(parts) >= 2 else None
                tries = parse_max_auth_tries(raw_val) if raw_val else None
                return "active", raw_val, tries

    return "not_found", None, None


def apply_max_auth_tries_logic(
    src_path: Path, dst_file_obj, target_value: str = "4"
) -> Tuple[bool, str]:
    """Menerapkan logika hardening MaxAuthTries ke file sementara."""
    found_parameter = False
    action_taken = ""

    with open(src_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line_stripped = line.strip()

            # 1. Terkomentar -> uncomment dan ubah ke target_value (4)
            if line_stripped.startswith("#"):
                uncommented = line_stripped[1:].lstrip()
                if uncommented.lower().startswith("maxauthtries"):
                    found_parameter = True
                    dst_file_obj.write(f"MaxAuthTries {target_value}\n")
                    action_taken = f"uncommented_and_set_to_{target_value}"
                    continue

            # 2. Aktif -> ubah nilainya ke target_value (4)
            elif line_stripped.lower().startswith("maxauthtries"):
                found_parameter = True
                dst_file_obj.write(f"MaxAuthTries {target_value}\n")
                action_taken = f"updated_to_{target_value}"
                continue

            dst_file_obj.write(line)

    # 3. Belum ada -> tambahkan parameter di akhir file
    if not found_parameter:
        dst_file_obj.write(f"\nMaxAuthTries {target_value}\n")
        action_taken = f"appended_new_parameter_{target_value}"

    return found_parameter, action_taken


def main():
    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="hardening.json",
        catalog="K04",
        cis_id="5.1.16",
        log_type="hardening",
    )

    lock_file_obj = acquire_lock(logger)

    try:
        # 1. Cek keberadaan file sshd_config
        if not check_sshd_config_exists(logger):
            logger.log(
                "FAILED",
                "Result",
                "Hasil Hardening: FAILED - File sshd_config tidak ditemukan.",
            )
            sys.exit(1)

        # 2. Cek status MaxAuthTries saat ini
        state, raw_val, tries = get_current_max_auth_tries(SSHD_CONFIG)

        # Jika sudah aktif dan nilainya berada di kisaran aman (1-4), batalkan hardening
        if state == "active" and tries is not None and 0 < tries <= 4:
            logger.log(
                "INFO",
                "Result",
                f"Hasil Hardening: CANCELLED - MaxAuthTries sudah dikonfigurasi secara aman ({tries} / '{raw_val}').",
            )
            sys.exit(0)

        # 3. Jalankan proses perubahan konfigurasi ke nilai standar CIS (4)
        with tempfile.NamedTemporaryFile(
            "w+", delete=False, prefix="sshd_config_"
        ) as tmp_file:
            tmp_config_path = Path(tmp_file.name)
            _, action = apply_max_auth_tries_logic(SSHD_CONFIG, tmp_file, target_value="4")

        # 4. Validasi sintaks file baru
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
                    f"Hardening berhasil: SUCCEED - MaxAuthTries dikonfigurasi ke 4 (Aksi: {action}).",
                )
            else:
                logger.log(
                    "WARNING",
                    "Result",
                    "Hardening berhasil: WARNING - Konfigurasi MaxAuthTries diubah, tetapi gagal merestart service SSH.",
                )
        else:
            if tmp_config_path.exists():
                tmp_config_path.unlink()
            logger.log(
                "ERROR",
                "Result",
                "Hardening berhasil: CANCELLED - Sintaks konfigurasi invalid! Hardening dibatalkan.",
            )
            sys.exit(1)

    except Exception as e:
        logger.log_error("K04", "hardening", e)
        sys.exit(1)

    finally:
        release_lock(lock_file_obj)


if __name__ == "__main__":
    main()