from __future__ import annotations
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Optional, Tuple

# -------------------------------------------------------------------------
# Import modul catalogutils via sys.path
# Path hardening.py: yoru-agent/catalog/K03/scripts/hardening.py
# -------------------------------------------------------------------------
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


def parse_grace_time_to_seconds(raw_value: str) -> Optional[int]:
    """Mengonversi nilai LoginGraceTime (misal: '60', '60s', '1m', '1h') ke satuan detik."""
    val = raw_value.strip().lower()
    try:
        if val.endswith("m"):
            return int(val[:-1]) * 60
        elif val.endswith("h"):
            return int(val[:-1]) * 3600
        elif val.endswith("d"):
            return int(val[:-1]) * 86400
        elif val.endswith("s"):
            return int(val[:-1])
        else:
            return int(val)
    except ValueError:
        return None


def get_current_login_grace_time(
    config_path: Path,
) -> Tuple[str, Optional[str], Optional[int]]:
    """Mengecek status dan nilai LoginGraceTime saat ini di sshd_config."""
    if not config_path.is_file():
        return "not_found", None, None

    with open(config_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line_stripped = line.strip()

            if line_stripped.startswith("#"):
                uncommented = line_stripped[1:].lstrip()
                if uncommented.lower().startswith("logingracetime"):
                    parts = uncommented.split()
                    raw_val = parts[1] if len(parts) >= 2 else None
                    sec = parse_grace_time_to_seconds(raw_val) if raw_val else None
                    return "commented", raw_val, sec

            elif line_stripped.lower().startswith("logingracetime"):
                parts = line_stripped.split()
                raw_val = parts[1] if len(parts) >= 2 else None
                sec = parse_grace_time_to_seconds(raw_val) if raw_val else None
                return "active", raw_val, sec

    return "not_found", None, None


def apply_login_grace_time_logic(
    src_path: Path, dst_file_obj, target_value: str = "60"
) -> Tuple[bool, str]:
    """Menerapkan logika hardening LoginGraceTime ke file sementara."""
    found_parameter = False
    action_taken = ""

    with open(src_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line_stripped = line.strip()

            # 1. Terkomentar -> uncomment dan ubah ke target_value (60)
            if line_stripped.startswith("#"):
                uncommented = line_stripped[1:].lstrip()
                if uncommented.lower().startswith("logingracetime"):
                    found_parameter = True
                    dst_file_obj.write(f"LoginGraceTime {target_value}\n")
                    action_taken = f"uncommented_and_set_to_{target_value}"
                    continue

            # 2. Aktif -> ubah nilainya ke target_value (60)
            elif line_stripped.lower().startswith("logingracetime"):
                found_parameter = True
                dst_file_obj.write(f"LoginGraceTime {target_value}\n")
                action_taken = f"updated_to_{target_value}"
                continue

            dst_file_obj.write(line)

    # 3. Belum ada -> tambahkan parameter di akhir file
    if not found_parameter:
        dst_file_obj.write(f"\nLoginGraceTime {target_value}\n")
        action_taken = f"appended_new_parameter_{target_value}"

    return found_parameter, action_taken


def main():
    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="hardening.json",
        catalog="K03",
        cis_id="5.1.13",
        log_type="hardening",
    )

    lock_file_obj = acquire_lock(logger)

    try:
        # 1. Cek keberadaan file sshd_config
        if not check_sshd_config_exists(logger):
            sys.exit(1)

        # 2. Cek status LoginGraceTime saat ini
        state, raw_val, seconds = get_current_login_grace_time(SSHD_CONFIG)

        # Jika sudah aktif dan nilainya berada di kisaran aman (1-60 detik), batalkan hardening
        if state == "active" and seconds is not None and 0 < seconds <= 60:
            logger.log(
                "INFO",
                f"Hardening Dibatalkan: LoginGraceTime sudah dikonfigurasi secara aman ({seconds} detik / '{raw_val}').",
            )
            sys.exit(0)

        # 3. Jalankan proses perubahan konfigurasi ke nilai standar CIS (60 detik)
        with tempfile.NamedTemporaryFile(
            "w+", delete=False, prefix="sshd_config_"
        ) as tmp_file:
            tmp_config_path = Path(tmp_file.name)
            _, action = apply_login_grace_time_logic(SSHD_CONFIG, tmp_file, target_value="60")

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
                    f"Hardening berhasil: LoginGraceTime dikonfigurasi ke 60 detik (Aksi: {action}).",
                )
            else:
                logger.log(
                    "WARNING",
                    "Konfigurasi LoginGraceTime diubah, tetapi gagal merestart service SSH.",
                )
        else:
            if tmp_config_path.exists():
                tmp_config_path.unlink()
            logger.log(
                "ERROR",
                "Sintaks konfigurasi invalid! Hardening dibatalkan.",
            )
            sys.exit(1)

    except Exception as e:
        logger.log("ERROR", f"Terjadi error saat proses hardening K03: {e}")
        sys.exit(1)

    finally:
        release_lock(lock_file_obj)


if __name__ == "__main__":
    main()