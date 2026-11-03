from __future__ import annotations
from pathlib import Path
from time import perf_counter
import subprocess
import shutil
import sys


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]  # Naik 3 level ke yoru-agent/

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import (
    SYSCTL_KEYS_ACCEPT_REDIRECTS, 
    SYSCTL_TARGET_ACCEPT_REDIRECTS,
    CATALOG_LOCKS,
)

from pipeline.catalogutils import (
    LogStatus,
    BaseLogger,
    load_taskfile_vars,
    acquire_lock,
    release_lock,
)


def check_sysctl_values() -> tuple[bool, str]:
    """
    Memeriksa konfigurasi ICMP Redirect berdasarkan nilai runtime sysctl.

    Semua parameter dalam SYSCTL_KEYS_ACCEPT_REDIRECTS harus bernilai 0.
    """
    sysctl_path = shutil.which("sysctl")

    if not sysctl_path:
        raise RuntimeError("Executable sysctl tidak ditemukan.")

    if not SYSCTL_KEYS_ACCEPT_REDIRECTS:
        raise RuntimeError("Daftar parameter ICMP Redirect tidak tersedia.")

    details = []
    errors = []
    non_compliant = False

    for key in SYSCTL_KEYS_ACCEPT_REDIRECTS:
        try:
            result = subprocess.run(
                [sysctl_path, "-n", key],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )

            if result.returncode != 0:
                error_message = result.stderr.strip() or "Gagal membaca nilai parameter."
                errors.append(f"{key}: {error_message}")
                continue

            value = result.stdout.strip()

            if value != SYSCTL_TARGET_ACCEPT_REDIRECTS:
                non_compliant = True
                details.append(f"{key}={value} (seharusnya {SYSCTL_TARGET_ACCEPT_REDIRECTS})")
            else:
                details.append(f"{key}={value} (OK)")

        except subprocess.TimeoutExpired:
            errors.append(f"{key}: Pemeriksaan mengalami timeout.")

        except OSError as exc:
            errors.append(f"{key}: {exc}")

    if errors:
        raise RuntimeError(
            "Gagal membaca satu atau lebih parameter sysctl: "
            + "; ".join(errors)
        )

    if non_compliant:
        return False, (
            "Parameter ICMP Redirect belum sesuai standar CIS: "
            + ", ".join(details)
        )

    return True, (
        "Semua parameter ICMP Redirect telah sesuai standar CIS: "
        + ", ".join(details)
    )


def main():
    task_vars = load_taskfile_vars(SCRIPT_DIR)

    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="audit.json",
        catalog=task_vars.get("ID", "K17"),
        nama=task_vars.get("NAMA", "Penolakan ICMP Redirect"),
        kode_cis=task_vars.get("KODE_CIS", "3.3.5"),
        judul_cis=task_vars.get("JUDUL_CIS", "Ensure icmp redirects are not accepted"),
        versi_cis=task_vars.get("VERSI_CIS", "Ubuntu 24.04 LTS Benchmark v2.0.0"),
        regulasi=task_vars.get("REGULASI", "Pasal 35, Pasal 39"),
        kepatuhan=task_vars.get("KEPATUHAN", "UU PDP No. 27/2022"),
        log_type="audit",
    )

    lock_name = CATALOG_LOCKS.get("K17", "icmp_redirects_audit")
    lock_file = acquire_lock(lock_name, logger)

    start = perf_counter()

    try:
        is_compliant, detail = check_sysctl_values()

        if is_compliant:
            logger.log(
                LogStatus.COMPLIANT,
                "Result",
                f"Hasil Audit: COMPLIANT - {detail}",
                duration_ms=(perf_counter() - start) * 1000,
            )
            sys.exit(0)
        else:
            logger.log(
                LogStatus.NON_COMPLIANT,
                "Result",
                f"Hasil Audit: NON_COMPLIANT - {detail}",
                duration_ms=(perf_counter() - start) * 1000,
            )
            sys.exit(1)

    except Exception as e:
        logger.log_error(
            "K17", 
            "audit", 
            e,
            duration_ms=(perf_counter() - start) * 1000,
        )
        sys.exit(2)
    finally:
        release_lock(lock_file)


if __name__ == "__main__":
    main()