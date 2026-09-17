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
    acquire_lock_sshd,
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


def get_login_grace_time_state(
    config_path: Path,
) -> Tuple[str, Optional[str], Optional[int]]:
    """Mengecek keberadaan dan nilai LoginGraceTime di sshd_config.

    Return:
        Tuple[state, raw_value, seconds]
        - state: 'not_found', 'commented', 'active'
        - raw_value: Nilai mentah di config (misal '60', '120')
        - seconds: Nilai dalam detik atau None
    """
    if not config_path.is_file():
        return "not_found", None, None

    with open(config_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line_stripped = line.strip()

            # 1. Baris Terkomentar
            if line_stripped.startswith("#"):
                uncommented = line_stripped[1:].lstrip()
                if uncommented.lower().startswith("logingracetime"):
                    parts = uncommented.split()
                    raw_val = parts[1] if len(parts) >= 2 else None
                    sec = parse_grace_time_to_seconds(raw_val) if raw_val else None
                    return "commented", raw_val, sec

            # 2. Baris Aktif
            elif line_stripped.lower().startswith("logingracetime"):
                parts = line_stripped.split()
                raw_val = parts[1] if len(parts) >= 2 else None
                sec = parse_grace_time_to_seconds(raw_val) if raw_val else None
                return "active", raw_val, sec

    return "not_found", None, None


def apply_rollback_login_grace_time(
    src_path: Path, dst_file_obj, rollback_value: str = "120"
) -> None:
    """Mengubah parameter LoginGraceTime aktif dari 60 menjadi nilai default (120)."""
    with open(src_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line_stripped = line.strip()

            if not line_stripped.startswith(
                "#"
            ) and line_stripped.lower().startswith("logingracetime"):
                dst_file_obj.write(f"LoginGraceTime {rollback_value}\n")
            else:
                dst_file_obj.write(line)


def main():
    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="rollback.json",
        catalog="K03",
        cis_id="5.1.13",
        log_type="rollback",
    )

    lock_file = acquire_lock_sshd(logger)

    try:
        if not check_sshd_config_exists(logger):
            logger.log(
                "FAILED", 
                "Result", 
                "Hasil Rollback: FAILED - File sshd_config tidak ditemukan."
            )
            sys.exit(1)

        # Cek status LoginGraceTime saat ini
        state, raw_val, seconds = get_login_grace_time_state(SSHD_CONFIG)

        # Syarat 1: Parameter tidak ditemukan -> Batalkan rollback
        if state == "not_found":
            logger.log(
                "FAILED",
                "Result",
                "Hasil Rollback: CANCELLED - Parameter LoginGraceTime tidak ditemukan di sshd_config.",
            )
            sys.exit(0)

        # Syarat 2: Parameter terkomentar (#) -> Batalkan rollback
        if state == "commented":
            logger.log(
                "FAILED",
                "Result",
                "Hasil Rollback: CANCELLED - Parameter LoginGraceTime dalam keadaan terkomentar (#).",
            )
            sys.exit(0)

        # Syarat 3: Jika nilainya sudah 120 (atau bukan 60/hasil hardening) -> Batalkan rollback
        if state == "active" and seconds is not None and seconds != 60:
            logger.log(
                "SKIPPED",
                "Result",
                f"Hasil Rollback: SKIPPED - LoginGraceTime tidak bernilai 60 detik (saat ini '{raw_val}').",
            )
            sys.exit(0)

        # 3. Jalankan proses rollback ke nilai default (120 detik)
        with tempfile.NamedTemporaryFile(
            "w+", delete=False, prefix="sshd_config_"
        ) as tmp_file:
            tmp_config_path = Path(tmp_file.name)
            apply_rollback_login_grace_time(SSHD_CONFIG, tmp_file, rollback_value="120")

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
                    "Hasil Rollback: SUCCEED - LoginGraceTime berhasil dikembalikan ke 120 detik.",
                )
            else:
                logger.log(
                    "WARNING",
                    "Result",
                    "Hasil Rollback: WARNING - Konfigurasi LoginGraceTime diubah ke 120, tetapi gagal merestart service SSH.",
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
        logger.log_error("K03", "rollback", e)

    finally:
        release_lock(lock_file)


if __name__ == "__main__":
    main()