from __future__ import annotations
from pathlib import Path
from time import perf_counter
import sys
import os
import shutil


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]  # Naik 3 level ke yoru-agent/

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import (
    SYSCTL_CONF,
    SYSCTL_KEY_TCP_SYNCOOKIES,
    SYSCTL_DEFAULT_TCP_SYNCOOKIES,
    CATALOG_LOCKS,
)

from pipeline.catalogutils import (
    LogStatus,
    BaseLogger,
    load_taskfile_vars,
    acquire_lock,
    release_lock,
    run_command,
    get_runtime_sysctl_value,
    write_config_atomically,
)


def update_sysctl_config(
    config_file: Path,
    sysctl_key: str,
    target_value: str,
) -> tuple[bytes, int, bool]:
    """
    Mengubah seluruh deklarasi aktif parameter sysctl
    ke nilai default.
    """

    if config_file.is_symlink():
        raise RuntimeError(
            f"File konfigurasi {config_file} merupakan symbolic link."
        )

    if not config_file.exists():
        raise RuntimeError(
            f"File konfigurasi {config_file} tidak ditemukan."
        )

    if not config_file.is_file():
        raise RuntimeError(
            f"Path konfigurasi {config_file} bukan file reguler."
        )

    original_content = config_file.read_bytes()
    original_mode = config_file.stat().st_mode & 0o777

    try:
        content = original_content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError(
            f"File konfigurasi {config_file} bukan teks UTF-8 yang valid."
        ) from exc

    updated_lines = []
    key_found = False
    changed = False

    for line in content.splitlines():
        stripped = line.strip()

        if not stripped or stripped.startswith("#") or "=" not in stripped:
            updated_lines.append(line)
            continue

        key, value = stripped.split("=", 1)
        normalized_key = key.strip().replace("/", ".")
        current_value = value.strip()

        if normalized_key == sysctl_key:
            key_found = True

            if current_value != target_value:
                changed = True

            updated_lines.append(
                f"{sysctl_key} = {target_value}"
            )
        else:
            updated_lines.append(line)

    if not key_found:
        raise RuntimeError(
            f"Parameter {sysctl_key} tidak ditemukan "
            f"di dalam {config_file.name}."
        )

    updated_content = ("\n".join(updated_lines) + "\n").encode("utf-8")

    if updated_content == original_content:
        changed = False

    if changed:
        write_config_atomically(
            config_file,
            updated_content,
            mode=original_mode,
        )

    return original_content, original_mode, changed


def restore_config(
    config_file: Path,
    original_content: bytes,
    original_mode: int,
) -> None:
    """Mengembalikan konfigurasi awal."""

    write_config_atomically(
        config_file,
        original_content,
        mode=original_mode,
    )


def perform_sysctl_rollback(
    sysctl_key: str,
    target_value: str,
) -> tuple[str, str]:
    """
    Melakukan rollback parameter sysctl ke nilai default.

    Status:
    - SUCCESS: Rollback berhasil diterapkan.
    - SKIPPED: Runtime dan konfigurasi sudah bernilai default.
    - CANCELLED: File atau parameter tidak ditemukan.
    - FAILED: Rollback gagal.
    """

    if os.geteuid() != 0:
        return (
            "FAILED",
            "Rollback harus dijalankan dengan hak akses root.",
        )

    sysctl_path = shutil.which("sysctl")

    if not sysctl_path:
        return (
            "FAILED",
            "Executable sysctl tidak ditemukan.",
        )

    config_file = SYSCTL_CONF

    if not config_file.exists():
        return (
            "CANCELLED",
            f"File konfigurasi {config_file.name} tidak ditemukan.",
        )

    if config_file.is_symlink() or not config_file.is_file():
        return (
            "FAILED",
            f"File konfigurasi {config_file} bukan file reguler "
            "atau merupakan symbolic link.",
        )

    original_content = config_file.read_bytes()
    original_mode = config_file.stat().st_mode & 0o777

    try:
        # Periksa seluruh deklarasi aktif pada file konfigurasi.
        try:
            config_text = original_content.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise RuntimeError(
                f"File konfigurasi {config_file} bukan teks UTF-8 yang valid."
            ) from exc

        current_values = []

        for line in config_text.splitlines():
            stripped = line.strip()

            if not stripped or stripped.startswith("#") or "=" not in stripped:
                continue

            key, value = stripped.split("=", 1)

            if key.strip().replace("/", ".") == sysctl_key:
                current_values.append(value.strip())

        if not current_values:
            return (
                "CANCELLED",
                f"Parameter {sysctl_key} tidak ditemukan "
                f"di dalam {config_file.name}.",
            )

        # Periksa kondisi runtime.
        runtime_value = get_runtime_sysctl_value(sysctl_key)

        # Lewati jika konfigurasi dan runtime sudah default.
        if (
            all(value == target_value for value in current_values)
            and runtime_value == target_value
        ):
            return (
                "SKIPPED",
                f"Parameter {sysctl_key} sudah berada pada "
                f"nilai default {target_value}.",
            )

        # Perbarui konfigurasi persisten.
        _, _, changed = update_sysctl_config(
            config_file=config_file,
            sysctl_key=sysctl_key,
            target_value=target_value,
        )

        # Terapkan konfigurasi ke kernel.
        run_command(
            [sysctl_path, "--system"],
            timeout=60,
        )

        # Validasi hasil rollback.
        runtime_value = get_runtime_sysctl_value(sysctl_key)

        if runtime_value != target_value:
            raise RuntimeError(
                f"Validasi rollback gagal. "
                f"Nilai aktual: {runtime_value}, "
                f"nilai yang diharapkan: {target_value}."
            )

        return (
            "SUCCESS",
            f"Parameter {sysctl_key} berhasil di-rollback "
            f"ke nilai default {target_value}. "
            f"Perubahan konfigurasi: {'Ya' if changed else 'Tidak'}.",
        )

    except Exception as exc:
        rollback_message = ""

        try:
            # Pulihkan file konfigurasi sebelum proses rollback.
            restore_config(
                config_file=config_file,
                original_content=original_content,
                original_mode=original_mode,
            )

            # Terapkan kembali konfigurasi awal.
            run_command(
                [sysctl_path, "--system"],
                timeout=60,
            )

            rollback_message = (
                " Konfigurasi awal berhasil dipulihkan."
            )

        except Exception as restore_exc:
            rollback_message = (
                f" PERINGATAN: Pemulihan konfigurasi gagal: "
                f"{restore_exc}"
            )

        return (
            "FAILED",
            f"Gagal melakukan rollback sysctl: {exc}."
            f"{rollback_message}",
        )
    

def main():
    task_vars = load_taskfile_vars(SCRIPT_DIR)

    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="rollback.json",
        catalog=task_vars.get("ID", "K19"),
        nama=task_vars.get("NAMA", "Pengaktifan TCP SYN Cookies"),
        kode_cis=task_vars.get("KODE_CIS", "3.3.10"),
        judul_cis=task_vars.get("JUDUL_CIS", "Ensure tcp syn cookies is enabled"),
        versi_cis=task_vars.get("VERSI_CIS", "Ubuntu 24.04 LTS Benchmark v2.0.0"),
        regulasi=task_vars.get("REGULASI", "Pasal 35, Pasal 39"),
        kepatuhan=task_vars.get("KEPATUHAN", "UU PDP No. 27/2022"),
        log_type="rollback",
    )

    lock_name = CATALOG_LOCKS.get("K19", "tcp_syncookies_rollback")
    lock_file = acquire_lock(lock_name, logger)

    start = perf_counter()

    try:
        
        status, detail = perform_sysctl_rollback(
            sysctl_key=SYSCTL_KEY_TCP_SYNCOOKIES,
            target_value=str(SYSCTL_DEFAULT_TCP_SYNCOOKIES),
        )

        if status == "SUCCESS":
            logger.log(
                LogStatus.SUCCESS,
                "Result", 
                f"Hasil Rollback: SUCCESS - {detail}",
                duration_ms=(perf_counter() - start) * 1000,
            )
            sys.exit(0)
        elif status == "SKIPPED":
            logger.log(
                LogStatus.SKIPPED,
                "Result", 
                f"Hasil Rollback: SKIPPED - {detail}",
                duration_ms=(perf_counter() - start) * 1000,
            )
            sys.exit(0)
        elif status == "CANCELLED":
            logger.log(
                LogStatus.SKIPPED, 
                "Result", 
                f"Hasil Rollback: CANCELLED - {detail}",
                duration_ms=(perf_counter() - start) * 1000,
            )
            sys.exit(0)
        else:
            logger.log(
                LogStatus.FAILED,
                "Result", 
                f"Hasil Rollback: FAILED - {detail}",
                duration_ms=(perf_counter() - start) * 1000,
            )
            sys.exit(1)
    except Exception as e:
        logger.log_error(
            "K19", 
            "rollback", 
            e,
            duration_ms=(perf_counter() - start) * 1000,
        )
        sys.exit(2)
    finally:
        release_lock(lock_file)


if __name__ == "__main__":
    main()