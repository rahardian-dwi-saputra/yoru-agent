from __future__ import annotations
from pathlib import Path
from typing import Tuple
from time import perf_counter
import subprocess
import sys

# Import modul catalogutils via sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]  # Naik 3 level ke yoru-agent/

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import SSHD_CONFIG, CATALOG_LOCKS

from pipeline.catalogutils import (
    LogStatus,
    BaseLogger,
    load_taskfile_vars,
    acquire_lock,
    release_lock,
    check_config_exists,
    get_non_root_users,
    check_config_parameter_value,
    get_effective_sshd_parameter
)


def check_ssh_key_validity(key_file: Path) -> Tuple[bool, str]:
    """Mengecek keabsahan kunci publik SSH menggunakan ssh-keygen -l."""
    try:
        result = subprocess.run(
            ["ssh-keygen", "-l", "-f", str(key_file)],
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return True, "Key valid"

        error_message = result.stderr.strip() or result.stdout.strip()
        return False, error_message or "Format kunci tidak valid."
    except Exception as e:
        return False, str(e)


def main():
    task_vars = load_taskfile_vars(SCRIPT_DIR)

    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="audit.json",
        catalog=task_vars.get("ID", "K02"),
        nama=task_vars.get("NAMA", "Login SSH menggunakan Password Dimatikan (Khusus SSH Key)"),
        kode_cis=task_vars.get("KODE_CIS", "-"),
        judul_cis=task_vars.get("JUDUL_CIS", "-"),
        versi_cis=task_vars.get("VERSI_CIS", "Ubuntu 24.04 LTS Benchmark v2.0.0"),
        regulasi=task_vars.get("REGULASI", "Pasal 35, Pasal 36, Pasal 39"),
        kepatuhan=task_vars.get("KEPATUHAN", "UU PDP No. 27/2022"),
        log_type="audit",
    )
    
    lock_name = CATALOG_LOCKS.get("K02", "sshd_config")
    lock_file = acquire_lock(lock_name, logger)

    start = perf_counter()
    
    try:
        if not check_config_exists(SSHD_CONFIG, "sshd_config", logger):
            logger.log(
                LogStatus.FAILED, 
                "Result", 
                f"Hasil Audit: FAILED - File {SSHD_CONFIG} tidak ditemukan.",
                duration_ms=(perf_counter() - start) * 1000,
            )
            sys.exit(1)

        # Pastikan sudah memiliki daftar user non-root
        users_with_home = get_non_root_users(include_home=True)
        if not users_with_home:
            logger.log(
                LogStatus.FAILED,
                "Note",
                "Hasil Audit: FAILED - Tidak ditemukan user non-root dengan shell aktif di sistem.",
                duration_ms=(perf_counter() - start) * 1000,
            )
            sys.exit(1)
        else:
            user_list_str = ", ".join([u[0] for u in users_with_home])
            logger.log(
                LogStatus.INFO,
                "Note",
                f"Ditemukan {len(users_with_home)} user non-root aktif: {user_list_str}"
            )

        findings: list[str] = []
        # Verifikasi SSH Key setiap user
        for username, home_dir in users_with_home:
            auth_keys_path = home_dir / ".ssh" / "authorized_keys"

            try:
                # Check 2: Keberadaan public key
                if not auth_keys_path.is_file():
                    findings.append(
                        f"- User '{username}' tidak memiliki file authorized_keys."
                    )
                    continue

                file_stat = auth_keys_path.stat()

                if file_stat.st_size == 0:
                    findings.append(
                        f"- File authorized_keys milik user '{username}' kosong."
                    )
                    continue

                # Periksa format kunci publik.
                is_valid, error_message = check_ssh_key_validity(
                    auth_keys_path
                )

                if not is_valid:
                    findings.append(
                        f"- File authorized_keys milik user '{username}' tidak valid: {error_message}"
                    )

                # Permission yang diharapkan: 600 (rw-------).
                file_mode = file_stat.st_mode & 0o777

                if file_stat.st_mode & 0o777 != 0o600:
                    findings.append(
                        f"- Permission authorized_keys milik user '{username}' adalah {oct(file_mode)}; seharusnya 0o600."
                    )
                    
            except OSError as exc:
                findings.append(
                    f"- File authorized_keys milik user '{username}' gagal diperiksa: {exc}."
                )


        if findings:
            logger.log(
                LogStatus.FAILED,
                "Result",
                "Hasil Audit: FAILED - Terdapat syarat pra-kondisi yang belum terpenuhi:\n" + "\n".join(findings),
                duration_ms=(perf_counter() - start) * 1000,
            )
            sys.exit(1)
        else:

            status, _ = check_config_parameter_value(
                SSHD_CONFIG, 
                "PasswordAuthentication"
            )

            if status == "commented":
                logger.log(
                    LogStatus.NON_COMPLIANT, 
                    "Result",
                    f"Hasil Audit: NON_COMPLIANT - Syarat terpenuhi, tapi Parameter PasswordAuthentication pada file {SSHD_CONFIG} dalam posisi dikomentari (belum diatur secara eksplisit).",
                    duration_ms=(perf_counter() - start) * 1000,
                )
                sys.exit(1)
            elif status == "active":
                password_auth = get_effective_sshd_parameter(
                    SSHD_CONFIG,
                    "PasswordAuthentication"
                )
                if password_auth == "no":
                    logger.log(
                        LogStatus.COMPLIANT,
                        "Result",
                        f"Hasil Audit: COMPLIANT - Syarat terpenuhi, parameter PasswordAuthentication pada file {SSHD_CONFIG} sudah di-set ke 'no'.",
                        duration_ms=(perf_counter() - start) * 1000,
                    )
                    sys.exit(0)
                elif password_auth == "yes":
                    logger.log(
                        LogStatus.NON_COMPLIANT, 
                        "Result",
                        f"Hasil Audit: NON_COMPLIANT - Syarat terpenuhi, tapi parameter PasswordAuthentication pada file {SSHD_CONFIG} bernilai 'yes' (seharusnya 'no').",
                        duration_ms=(perf_counter() - start) * 1000,
                    )
                    sys.exit(1)
            else:
                logger.log(
                    LogStatus.NON_COMPLIANT,
                    "Result",
                    f"Hasil Audit: NON_COMPLIANT - Syarat terpenuhi, tapi parameter PasswordAuthentication pada file {SSHD_CONFIG} tidak ditemukan.",
                    duration_ms=(perf_counter() - start) * 1000,
                )
                sys.exit(1)


    except Exception as e:
        logger.log_error(
            "K02", 
            "audit", 
            e,
            duration_ms=(perf_counter() - start) * 1000,
        )
        sys.exit(2)

    finally:
        release_lock(lock_file)


if __name__ == "__main__":
    main()