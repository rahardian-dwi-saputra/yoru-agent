from __future__ import annotations
from pathlib import Path
from time import perf_counter
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

from config.settings import (
    SSHD_CONFIG, 
    SSH_SERVICE_NAME, 
    CATALOG_LOCKS
)

from pipeline.catalogutils import (
    LogStatus,
    BaseLogger,
    acquire_lock,
    release_lock,
    check_config_exists,
    check_config_parameter_value,
    get_effective_sshd_parameter,
    set_config_parameter_value,
    restart_system_service,
)


def main():
    
    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="rollback.json",
        catalog="K01",
        cis_id="5.1.20",
        regulasi="Pasal 35, Pasal 36, Pasal 39",
        kepatuhan="UU PDP No. 27/2022",
        log_type="rollback",
    )

    lock_name = CATALOG_LOCKS.get("K01", "sshd_config")
    lock_file = acquire_lock(lock_name, logger)

    start = perf_counter()

    try:
        if not check_config_exists(SSHD_CONFIG, "sshd_config", logger):
            logger.log(
                LogStatus.FAILED,
                "Result", 
                f"Hasil Rollback: FAILED - File {SSHD_CONFIG} tidak ditemukan.",
                duration_ms=(perf_counter() - start) * 1000,
            )
            sys.exit(1)

        status, _ = check_config_parameter_value(SSHD_CONFIG, "PermitRootLogin")

        if status == "not_found":
            logger.log(
                LogStatus.FAILED,
                "Result",
                f"Hasil Rollback: CANCELLED - Parameter PermitRootLogin tidak ditemukan di file {SSHD_CONFIG}",
                duration_ms=(perf_counter() - start) * 1000,
            )
            sys.exit(1)
        elif status == "commented":
            logger.log(
                LogStatus.FAILED,
                "Result",
                f"Hasil Rollback: CANCELLED - Parameter PermitRootLogin pada file {SSHD_CONFIG} dalam keadaan terkomentar (#).",
                duration_ms=(perf_counter() - start) * 1000,
            )
            sys.exit(1)
        elif status == "active":
            value = get_effective_sshd_parameter(
                config_file=SSHD_CONFIG,
                parameter="PermitRootLogin",
            )
            if value and value.lower() == "yes":
                logger.log(
                    LogStatus.SKIPPED,
                    "Result",
                    "Hasil Rollback: SKIPPED - Parameter PermitRootLogin sudah bernilai 'yes'.",
                    duration_ms=(perf_counter() - start) * 1000,
                )
                sys.exit(0)
            elif value and value.lower() != "no":
                # Jika bernilai bukan 'no' (misal: prohibit-password / forced-commands-only)
                logger.log(
                    LogStatus.FAILED,
                    "Result",
                    f"Hasil Rollback: CANCELLED - PermitRootLogin bernilai '{value}' (hanya 'no' yang diubah ke 'yes').",
                    duration_ms=(perf_counter() - start) * 1000,
                )
                sys.exit(1)

        # Buat salinan sementara untuk proses modifikasi dan uji sintaks yang aman
        with tempfile.NamedTemporaryFile(
            "w+", delete=False, prefix="sshd_config_"
        ) as tmp_file:
            tmp_config_path = Path(tmp_file.name)
      
        # Salin konten file asli ke file sementara
        shutil.copy2(SSHD_CONFIG, tmp_config_path)
      
        # Terapkan perubahan parameter
        success_set = set_config_parameter_value(
            tmp_config_path, "PermitRootLogin", "yes"
        )
      
        if not success_set:
            if tmp_config_path.exists():
                tmp_config_path.unlink()
            logger.log(
                LogStatus.FAILED,
                "Result",
                "Hasil Hardening: FAILED - Gagal menerapkan parameter PermitRootLogin pada file konfigurasi.",
                duration_ms=(perf_counter() - start) * 1000,
            )
            sys.exit(1)

        # Validasi sintaks file sementara menggunakan sshd -t -f
        validate_cmd = subprocess.run(
            ["sshd", "-t", "-f", str(tmp_config_path)], capture_output=True
        )

        if validate_cmd.returncode == 0:
            # Timpa file utama secara atomic
            shutil.move(str(tmp_config_path), str(SSHD_CONFIG))
            os.chmod(SSHD_CONFIG, 0o600)

            # Restart layanan SSH untuk menerapkan perubahan
            if restart_system_service(SSH_SERVICE_NAME):
                logger.log(
                    LogStatus.SUCCESS,
                    "Result",
                    "Hasil Rollback: SUCCEED - Parameter PermitRootLogin berhasil dikembalikan ke 'yes'.",
                    duration_ms=(perf_counter() - start) * 1000,
                )
                sys.exit(0)
            else:
                logger.log(
                    LogStatus.WARNING,
                    "Result",
                    "Hasil Rollback: WARNING - Konfigurasi diubah ke 'yes', tetapi gagal merestart service SSH.",
                    duration_ms=(perf_counter() - start) * 1000,
                )
                sys.exit(1)

    except Exception as e:
        logger.log_error(
            "K01", 
            "rollback", 
            e,
            duration_ms=(perf_counter() - start) * 1000,
        )
        sys.exit(2)
    finally:
        release_lock(lock_file)


if __name__ == "__main__":
    main()