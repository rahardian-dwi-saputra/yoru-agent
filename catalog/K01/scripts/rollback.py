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
    release_lock,
    restart_ssh_service,
    check_sshd_config_exists,
)


def check_permit_root_login_state(
    config_path: Path,
) -> Tuple[str, Optional[str]]:
    """Mengecek keberadaan dan nilai PermitRootLogin di sshd_config.

    Return:
        Tuple[state, value]
        - state: 'not_found', 'commented', 'active'
        - value: Nilai parameter (misal 'yes', 'no') atau None jika tidak ada
    """
    if not config_path.is_file():
        return "not_found", None

    with open(config_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line_stripped = line.strip()

            # Cek jika baris berkomentar
            if line_stripped.startswith("#"):
                uncommented = line_stripped[1:].lstrip()
                if uncommented.lower().startswith("permitrootlogin"):
                    parts = uncommented.split()
                    val = parts[1] if len(parts) >= 2 else None
                    return "commented", val

            # Cek jika baris aktif
            elif line_stripped.lower().startswith("permitrootlogin"):
                parts = line_stripped.split()
                val = parts[1] if len(parts) >= 2 else None
                return "active", val

    return "not_found", None


def apply_rollback_logic(src_path: Path, dst_file_obj) -> None:
    """Mengubah parameter PermitRootLogin aktif yang bernilai 'no' menjadi 'yes'."""
    with open(src_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line_stripped = line.strip()

            # Ubah HANYA baris aktif PermitRootLogin
            if not line_stripped.startswith(
                "#"
            ) and line_stripped.lower().startswith("permitrootlogin"):
                dst_file_obj.write("PermitRootLogin yes\n")
            else:
                dst_file_obj.write(line)


def main():
    
    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="rollback.json",
        catalog="K01",
        cis_id="5.1.20",
        log_type="rollback",
    )

    lock_file = acquire_lock(logger)

    try:
        if not check_sshd_config_exists(logger):
            logger.log(
                "FAILED", 
                "Result", 
                "Hasil Rollback: FAILED - File sshd_config tidak ditemukan."
            )
            sys.exit(1)

        # Cek status parameter PermitRootLogin di sshd_config
        state, value = check_permit_root_login_state(SSHD_CONFIG)

        # Syarat 1: Tidak ada parameter PermitRootLogin di SSHD_CONFIG
        if state == "not_found":
            logger.log(
                "FAILED",
                "Result",
                "Hasil Rollback: CANCELLED - Parameter PermitRootLogin tidak ditemukan di sshd_config.",
            )
            sys.exit(0)

        # Syarat 2: Parameter PermitRootLogin dalam posisi Comment ('#')
        if state == "commented":
            logger.log(
                "FAILED",
                "Result",
                "Hasil Rollback: CANCELLED - Parameter PermitRootLogin dalam keadaan terkomentar (#).",
            )
            sys.exit(0)

        # Syarat 3: Parameter PermitRootLogin sudah bernilai 'yes'
        if state == "active" and value and value.lower() == "yes":
            logger.log(
                "SKIPPED",
                "Result",
                "Hasil Rollback: SKIPPED - PermitRootLogin sudah bernilai 'yes'.",
            )
            sys.exit(0)

        # Syarat 4: Jika bernilai bukan 'no' (misal: prohibit-password / forced-commands-only)
        if state == "active" and value and value.lower() != "no":
            logger.log(
                "FAILED",
                "Result",
                f"Hasil Rollback: CANCELLED - PermitRootLogin bernilai '{value}' (hanya 'no' yang diubah ke 'yes').",
            )
            sys.exit(0)

        # Proses perubahan config (Hanya jika bernilai 'no')
        with tempfile.NamedTemporaryFile(
            "w+", delete=False, prefix="sshd_config_"
        ) as tmp_file:
            tmp_config_path = Path(tmp_file.name)
            apply_rollback_logic(SSHD_CONFIG, tmp_file)

        # Validasi sintaks file sementara menggunakan sshd -t -f
        validate_cmd = subprocess.run(
            ["sshd", "-t", "-f", str(tmp_config_path)], capture_output=True
        )

        if validate_cmd.returncode == 0:
            # Timpa file utama secara atomic
            shutil.move(str(tmp_config_path), str(SSHD_CONFIG))
            os.chmod(SSHD_CONFIG, 0o600)

            if restart_ssh_service():
                logger.log(
                    "SUCCESS",
                    "Result",
                    "Hasil Rollback: SUCCEED - PermitRootLogin berhasil dikembalikan ke 'yes'. Konfigurasi lain tetap terjaga.",
                )
            else:
                logger.log(
                    "WARNING",
                    "Result",
                    "Hasil Rollback: WARNING - Konfigurasi diubah ke 'yes', tetapi gagal merestart service SSH.",
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
        logger.log_error("K01", "rollback", e)

    finally:
        release_lock(lock_file)


if __name__ == "__main__":
    main()