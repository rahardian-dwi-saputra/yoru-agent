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
    temp_config: Path | None = None
    original_config: Path | None = None

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

        # Siapkan konfigurasi kandidat dan salinan pemulihan.
        with tempfile.NamedTemporaryFile(
            prefix=".sshd-rollback-",
            dir=SSHD_CONFIG.parent,
            delete=False,
        ) as tmp:
            temp_config = Path(tmp.name)

        with tempfile.NamedTemporaryFile(
            prefix=".sshd-original-",
            dir=SSHD_CONFIG.parent,
            delete=False,
        ) as tmp:
            original_config = Path(tmp.name)

        shutil.copy2(SSHD_CONFIG, temp_config)
        shutil.copy2(SSHD_CONFIG, original_config)
        os.chmod(temp_config, 0o600)

        # Ubah parameter pada file kandidat.
        if not set_config_parameter_value(
            temp_config,
            "PermitRootLogin",
            "yes",
        ):
            logger.log(
                LogStatus.FAILED,
                "Result",
                f"Hasil Rollback: FAILED - tidak dapat mengubah PermitRootLogin.",
                duration_ms=(perf_counter() - start) * 1000,
            )
            sys.exit(1)

        # Validasi sintaks konfigurasi.
        sshd_path = shutil.which("sshd")
        if sshd_path is None:
            raise RuntimeError("Executable sshd tidak ditemukan.")

        validation = subprocess.run(
            [sshd_path, "-t", "-f", str(temp_config)],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )

        if validation.returncode != 0:
            detail = (
                validation.stderr.strip()
                or "Sintaks konfigurasi tidak valid."
            )
            logger.log(
                LogStatus.FAILED,
                "Result",
                f"Hasil Rollback: FAILED - validasi sshd gagal: {detail}",
                duration_ms=(perf_counter() - start) * 1000,
            )
            sys.exit(1)

        # Pastikan nilai efektif kandidat benar-benar 'yes'.
        effective_value = get_effective_sshd_parameter(
            config_file=temp_config,
            parameter="PermitRootLogin",
        )

        if effective_value.lower() != "yes":
            logger.log(
                LogStatus.FAILED,
                "Result",
                f"Hasil Rollback: FAILED - nilai efektif kandidat adalah {effective_value}', bukan 'yes'.",
                duration_ms=(perf_counter() - start) * 1000,
            )
            sys.exit(1)

        # Terapkan konfigurasi yang telah tervalidasi.
        os.replace(temp_config, SSHD_CONFIG)
        temp_config = None

        if not restart_system_service(SSH_SERVICE_NAME):
            # Pulihkan file konfigurasi sebelumnya.
            os.replace(original_config, SSHD_CONFIG)
            original_config = None
        
            if restart_system_service(SSH_SERVICE_NAME):
                logger.log(
                    LogStatus.WARNING,
                    "Result",
                    f"Hasil Rollback: WARNING - Restart SSH gagal; konfigurasi lama dipulihkan.",
                    duration_ms=(perf_counter() - start) * 1000,
                )
            else:
                logger.log(
                    LogStatus.ERROR,
                    "Result",
                    f"Hasil Rollback: FAILED - restart SSH gagal dan restart setelah rollback juga gagal.",
                    duration_ms=(perf_counter() - start) * 1000,
                )  
            sys.exit(2)

        logger.log(
            LogStatus.SUCCESS,
            "Result",
            f"Hasil Rollback: SUCCEED - PermitRootLogin berhasil dinonaktifkan dan service SSH berhasil direstart.",
            duration_ms=(perf_counter() - start) * 1000,
        )
        sys.exit(0) 
            
    except Exception as e:
        logger.log_error(
            "K01", 
            "rollback", 
            e,
            duration_ms=(perf_counter() - start) * 1000,
        )
        sys.exit(2)
    finally:
        for path in (temp_config, original_config):
            if path is not None:
                try:
                    path.unlink(missing_ok=True)
                except OSError as exc:
                    logger.log(
                        LogStatus.WARNING,
                        "Note",
                        f"Gagal membersihkan file sementara: {exc}",
                    )
                    
        release_lock(lock_file)


if __name__ == "__main__":
    main()