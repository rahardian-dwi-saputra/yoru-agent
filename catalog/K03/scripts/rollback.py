from __future__ import annotations
from pathlib import Path
from typing import Optional
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
    load_taskfile_vars,
    acquire_lock,
    release_lock,
    check_config_exists,
    check_config_parameter_value,
    get_effective_sshd_parameter,
    set_config_parameter_value,
    restart_system_service
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


def main():
    task_vars = load_taskfile_vars(SCRIPT_DIR)

    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="rollback.json",
        catalog=task_vars.get("ID", "K03"),
        nama=task_vars.get("NAMA", "Membatasi Waktu Login SSH (LoginGraceTime)"),
        kode_cis=task_vars.get("KODE_CIS", "5.1.13"),
        judul_cis=task_vars.get("JUDUL_CIS", "Ensure sshd LoginGraceTime is configured"),
        versi_cis=task_vars.get("VERSI_CIS", "Ubuntu 24.04 LTS Benchmark v2.0.0"),
        regulasi=task_vars.get("REGULASI", "Pasal 35, Pasal 39"),
        kepatuhan=task_vars.get("KEPATUHAN", "UU PDP No. 27/2022"),
        log_type="rollback",
    )

    lock_name = CATALOG_LOCKS.get("K03", "sshd_config")
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

        status, _ = check_config_parameter_value(SSHD_CONFIG, "LoginGraceTime")

        if status == "not_found":
            logger.log(
                LogStatus.FAILED,
                "Result",
                f"Hasil Rollback: CANCELLED - Parameter LoginGraceTime tidak ditemukan di file {SSHD_CONFIG}",
                duration_ms=(perf_counter() - start) * 1000,
            )
            sys.exit(1)
        elif status == "commented":
            logger.log(
                LogStatus.FAILED,
                "Result",
                f"Hasil Rollback: CANCELLED - Parameter LoginGraceTime pada file {SSHD_CONFIG} dalam keadaan terkomentar (#).",
                duration_ms=(perf_counter() - start) * 1000,
            )
            sys.exit(1)
        elif status == "active":
            login_grace_time = get_effective_sshd_parameter(
                config_file=SSHD_CONFIG,
                parameter="LoginGraceTime",
            )

            grace_seconds = parse_grace_time_to_seconds(login_grace_time)

            if grace_seconds == 120:
                logger.log(
                    LogStatus.SKIPPED,
                    "Result",
                    f"Hasil Rollback: SKIPPED - LoginGraceTime sudah bernilai 120 detik (saat ini '{login_grace_time}').",
                    duration_ms=(perf_counter() - start) * 1000,
                )
                sys.exit(0)

            # Buat salinan sementara untuk proses modifikasi dan uji sintaks yang aman
            with tempfile.NamedTemporaryFile(
                prefix=".sshd-candidate-",
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

            # Salin konten file asli ke file sementara
            shutil.copy2(SSHD_CONFIG, temp_config)
            shutil.copy2(SSHD_CONFIG, original_config)
            os.chmod(temp_config, 0o600)
            
            # Terapkan perubahan parameter pada file sementara
            if not set_config_parameter_value(
                temp_config,
                "LoginGraceTime",
                "120",
            ):
                logger.log(
                    LogStatus.FAILED,
                    "Result",
                    "Hasil Rollback: FAILED - Gagal menerapkan nilai parameter LoginGraceTime '120' pada file konfigurasi.",
                    duration_ms=(perf_counter() - start) * 1000,
                )
                sys.exit(1)

            sshd = shutil.which("sshd")
            if sshd is None:
                raise RuntimeError("Executable sshd tidak ditemukan.")
                    
            # Validasi sintaks file konfigurasi sementara menggunakan perintah sshd -t
            validation = subprocess.run(
                [sshd, "-t", "-f", str(temp_config)],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )
            
            if validation.returncode != 0:
                detail = validation.stderr.strip() or "Sintaks konfigurasi tidak valid."
                logger.log(
                    LogStatus.FAILED,
                    "Result",
                    f"Hasil Rollback: FAILED - Validasi sshd gagal: {detail}",
                    duration_ms=(perf_counter() - start) * 1000,
                )
                sys.exit(1)

            effective_value = get_effective_sshd_parameter(
                temp_config,
                "LoginGraceTime",
            )
            if effective_value.lower() != "120":
                logger.log(
                    LogStatus.FAILED,
                    "Result",
                    f"Hasil Rollback: FAILED - Nilai efektif kandidat adalah '{effective_value}', bukan '120'.",
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
                    sys.exit(1)
                else:
                    logger.log(
                        LogStatus.ERROR,
                        "Result",
                        f"Hasil Rollback: ERROR - restart SSH gagal dan restart setelah rollback juga gagal.",
                        duration_ms=(perf_counter() - start) * 1000,
                    )  
                    sys.exit(2)

            logger.log(
                LogStatus.SUCCESS,
                "Result",
                f"Hasil Rollback: SUCCEED - Waktu login SSH berhasil dikembalikan ke 120 detik dan service SSH berhasil direstart.",
                duration_ms=(perf_counter() - start) * 1000,
            )
            sys.exit(0) 

    except Exception as e:
        logger.log_error(
            "K03", 
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