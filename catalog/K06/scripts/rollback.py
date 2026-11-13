from __future__ import annotations
from pathlib import Path
from time import perf_counter
import os
import shutil
import subprocess
import sys
import tempfile
import re


# Import modul catalogutils via sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]  # Naik 3 level ke yoru-agent/

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import (
    SSHD_CONFIG, 
    SSH_SERVICE_NAME, 
    APPROVED_MACS_LIST, 
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
    restart_system_service
)


HARDENED_MACS_SET = set(APPROVED_MACS_LIST)

def apply_rollback_macs(src_path: Path, dst_path: Path) -> int:
    """
    Mengomentari seluruh direktif MACs yang masih aktif.

    Mengembalikan jumlah direktif yang berhasil dikomentari.
    """
    count = 0

    with open(src_path, "r", encoding="utf-8", errors="ignore", newline="") as src:
        with open(dst_path, "w", encoding="utf-8", newline="") as dst:
            for line in src:
                stripped = line.lstrip()

                # Cocokkan nama direktif secara tepat.
                if re.match(r"(?i)^MACs(?:\s|$)", stripped):
                    indent = line[:len(line) - len(stripped)]
                    dst.write(f"{indent}# {stripped}")
                    count += 1
                else:
                    dst.write(line)

    return count

def validate_sshd_config(config_file: Path) -> None:
    """Memvalidasi sintaks konfigurasi SSH menggunakan sshd -t."""
    sshd = shutil.which("sshd")

    if not sshd:
        raise RuntimeError("Executable sshd tidak ditemukan.")

    result = subprocess.run(
        [sshd, "-t", "-f", str(config_file)],
        capture_output=True,
        text=True,
        timeout=15,
        check=False,
    )

    if result.returncode != 0:
        detail = result.stderr.strip() or "Sintaks konfigurasi tidak valid."
        raise RuntimeError(f"Validasi sshd gagal: {detail}")



def main():
    task_vars = load_taskfile_vars(SCRIPT_DIR)

    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="rollback.json",
        catalog=task_vars.get("ID", "K06"),
        nama=task_vars.get("NAMA", "Pengaturan MACs SSH yang Aman (Integritas Pesan)"),
        kode_cis=task_vars.get("KODE_CIS", "5.1.15"),
        judul_cis=task_vars.get("JUDUL_CIS", "Ensure sshd MACs are configured"),
        versi_cis=task_vars.get("VERSI_CIS", "Ubuntu 24.04 LTS Benchmark v2.0.0"),
        regulasi=task_vars.get("REGULASI", "Pasal 35, Pasal 39"),
        kepatuhan=task_vars.get("KEPATUHAN", "UU PDP No. 27/2022"),
        log_type="rollback",
    )

    lock_name = CATALOG_LOCKS.get("K06", "sshd_config")
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

        status, _ = check_config_parameter_value(SSHD_CONFIG, "MACs")

        if status == "not_found":
            logger.log(
                LogStatus.FAILED,
                "Result",
                f"Hasil Rollback: CANCELLED - Parameter MACs tidak ditemukan di file {SSHD_CONFIG}",
                duration_ms=(perf_counter() - start) * 1000,
            )
            sys.exit(1)
        elif status == "commented":
            logger.log(
                LogStatus.FAILED,
                "Result",
                f"Hasil Rollback: CANCELLED - Parameter MACs pada file {SSHD_CONFIG} dalam keadaan terkomentar (#).",
                duration_ms=(perf_counter() - start) * 1000,
            )
            sys.exit(1)
        elif status == "active":
            macs = get_effective_sshd_parameter(
                config_file=SSHD_CONFIG,
                parameter="MACs",
            )

            mac_set = {
                mac.strip()
                for mac in macs.split(",")
                if mac.strip()
            }

            if mac_set != HARDENED_MACS_SET:
                logger.log(
                    LogStatus.SKIPPED,
                    "Result",
                    "Hasil Rollback: SKIPPED - Konfigurasi MACs aktif saat ini bukan berasal dari hasil hardening K06.",
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

            # Komentari direktif Ciphers pada kandidat.
            commented_count = apply_rollback_macs(
                SSHD_CONFIG,
                temp_config,
            )

            if commented_count == 0:
                logger.log(
                    LogStatus.SKIPPED,
                    "Result",
                    "Hasil Rollback: SKIPPED - Tidak ditemukan direktif MACs aktif untuk dikomentari.",
                    duration_ms=(perf_counter() - start) * 1000,
                )
                sys.exit(0)

            # Validasi sintaks konfigurasi kandidat.
            validate_sshd_config(temp_config)

            # Pastikan direktif MACs pada file kandidat sudah dikomentari.
            candidate_status, _ = check_config_parameter_value(
                temp_config,
                "MACs",
            )

            if candidate_status != "commented":
                raise RuntimeError(
                    "Direktif MACs masih aktif setelah proses rollback."
                )


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
                f"Hasil Rollback: SUCCEED - {commented_count} direktif MACs berhasil dikomentari, SSH kembali menggunakan konfigurasi macs bawaan dan service SSH berhasil direstart.",
                duration_ms=(perf_counter() - start) * 1000,
            )
            sys.exit(0)

    except Exception as e:
        logger.log_error(
            "K06", 
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