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
    APPROVED_KEX_LIST, 
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
    create_ssh_backup,
    set_config_parameter_value,
    restart_system_service
)


HARDENED_KEX_VALUE = ",".join(APPROVED_KEX_LIST)
APPROVED_KEX_SET = set(APPROVED_KEX_LIST)

def main():
    task_vars = load_taskfile_vars(SCRIPT_DIR)

    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="hardening.json",
        catalog=task_vars.get("ID", "K07"),
        nama=task_vars.get("NAMA", "Pengaturan KexAlgorithms SSH yang Aman"),
        kode_cis=task_vars.get("KODE_CIS", "5.1.12"),
        judul_cis=task_vars.get("JUDUL_CIS", "Ensure sshd KexAlgorithms are configured"),
        versi_cis=task_vars.get("VERSI_CIS", "Ubuntu 24.04 LTS Benchmark v2.0.0"),
        regulasi=task_vars.get("REGULASI", "Pasal 35, Pasal 39"),
        kepatuhan=task_vars.get("KEPATUHAN", "UU PDP No. 27/2022"),
        log_type="hardening",
    )

    lock_name = CATALOG_LOCKS.get("K07", "sshd_config")
    lock_file = acquire_lock(lock_name, logger)

    start = perf_counter()
    temp_config: Path | None = None
    original_config: Path | None = None

    try:
        if not check_config_exists(SSHD_CONFIG, "sshd_config", logger):
            logger.log(
                LogStatus.FAILED,
                "Result",
                f"Hasil Hardening: FAILED - File {SSHD_CONFIG} tidak ditemukan.",
                duration_ms=(perf_counter() - start) * 1000,
            )
            sys.exit(1)

        # Cek apakah KexAlgorithms sudah dihardening
        status, _ = check_config_parameter_value(
            SSHD_CONFIG, 
            "KexAlgorithms"
        )
        if status == "active":
            kex_algorithms = get_effective_sshd_parameter(
                config_file=SSHD_CONFIG,
                parameter="KexAlgorithms",
            )

            kex_algorithm_set = {
                algorithm.strip()
                for algorithm in kex_algorithms.split(",")
                if algorithm.strip()
            }

            if kex_algorithm_set.issubset(APPROVED_KEX_SET) and kex_algorithm_set == APPROVED_KEX_SET:
                logger.log(
                    LogStatus.SKIPPED,
                    "Result",
                    f"Hasil Hardening: SKIPPED - Parameter KexAlgorithms pada file {SSHD_CONFIG} sudah ter-hardening dan sesuai standar CIS.",
                    duration_ms=(perf_counter() - start) * 1000,
                )
                sys.exit(0)

        # Buat backup konfigurasi sebelum melakukan perubahan.
        success_backup, backup_msg = create_ssh_backup(logger)
        if not success_backup:
            logger.log(
                LogStatus.FAILED,
                "Result", 
                f"Hasil Hardening: BackupFailed - {backup_msg}",
                duration_ms=(perf_counter() - start) * 1000, 
            )
            sys.exit(1)

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
            "KexAlgorithms",
            HARDENED_KEX_VALUE
        ):
            logger.log(
                LogStatus.FAILED,
                "Result",
                "Hasil Hardening: FAILED - Gagal menerapkan nilai parameter KexAlgorithms pada file konfigurasi.",
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
                f"Hasil Hardening: FAILED - Validasi sshd gagal: {detail}",
                duration_ms=(perf_counter() - start) * 1000,
            )
            sys.exit(1)

        effective_value = get_effective_sshd_parameter(
            temp_config,
            "KexAlgorithms",
        )

        if effective_value != HARDENED_KEX_VALUE:
            logger.log(
                LogStatus.FAILED,
                "Result",
                f"Hasil Hardening: FAILED - Nilai efektif kandidat adalah '{effective_value}', bukan '{HARDENED_KEX_VALUE}'.",
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
                    f"Hasil Hardening: WARNING - Restart SSH gagal; konfigurasi lama dipulihkan.",
                    duration_ms=(perf_counter() - start) * 1000,
                )
                sys.exit(1)
            else:
                logger.log(
                    LogStatus.ERROR,
                    "Result",
                    f"Hasil Hardening: ERROR - restart SSH gagal dan restart setelah rollback juga gagal.",
                    duration_ms=(perf_counter() - start) * 1000,
                )  
                sys.exit(2)

        logger.log(
            LogStatus.SUCCESS,
            "Result",
            f"Hasil Hardening: SUCCEED - Parameter 'KexAlgorithms' pada file {SSHD_CONFIG} berhasil diperbarui dan service SSH berhasil direstart.",
            duration_ms=(perf_counter() - start) * 1000,
        )
        sys.exit(0)

    except Exception as e:
        logger.log_error(
            "K07", 
            "hardening", 
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
                        f"Gagal menghapus file sementara: {exc}",
                    )

        release_lock(lock_file)


if __name__ == "__main__":
    main()