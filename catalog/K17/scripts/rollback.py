from __future__ import annotations
from pathlib import Path
from time import perf_counter
import subprocess
import sys
import os
import stat
import shutil

# Import modul catalogutils via sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]  # Naik 3 level ke yoru-agent/

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import (
    SYSCTL_CONF,
    SYSCTL_KEYS_ACCEPT_REDIRECTS,
    SYSCTL_DEFAULT_ACCEPT_REDIRECTS,
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

def get_config_mode(config_file: Path) -> int:
    """Mengambil permission file konfigurasi."""
    if config_file.is_symlink():
        raise RuntimeError(
            f"File konfigurasi tidak boleh berupa symbolic link: {config_file}"
        )

    if config_file.exists():
        if not config_file.is_file():
            raise RuntimeError(
                f"Path konfigurasi bukan file biasa: {config_file}"
            )

        return stat.S_IMODE(config_file.stat().st_mode)

    return 


def get_config_values(
    content: str,
    sysctl_keys: list[str],
) -> dict[str, list[str]]:
    """Mengambil seluruh deklarasi aktif parameter sysctl."""
    values = {key: [] for key in sysctl_keys}

    for line in content.splitlines():
        stripped = line.strip()

        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue

        key, _, value = stripped.partition("=")
        key = key.strip()

        if key in values:
            values[key].append(value.strip())

    return values


def build_rollback_config(
    content: str,
    sysctl_keys: list[str],
    default_value: str,
) -> str:
    """Mengubah atau menambahkan parameter ke nilai default."""
    values = get_config_values(content, sysctl_keys)
    new_lines = []
    processed_keys = set()

    for line in content.splitlines(keepends=True):
        stripped = line.strip()

        if stripped and not stripped.startswith("#") and "=" in stripped:
            key, _, _ = stripped.partition("=")
            key = key.strip()

            if key in values:
                new_lines.append(f"{key} = {default_value}\n")
                processed_keys.add(key)
                continue

        new_lines.append(line)

    missing_keys = [
        key for key in sysctl_keys if key not in processed_keys
    ]

    if missing_keys:
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines.append("\n")

        if new_lines and new_lines[-1].strip():
            new_lines.append("\n")

        for key in missing_keys:
            new_lines.append(f"{key} = {default_value}\n")

    return "".join(new_lines)


def restore_config(
    config_file: Path,
    original_content: bytes,
    original_mode: int,
    sysctl_path: str,
) -> None:
    """Mengembalikan konfigurasi sebelum rollback."""
    write_config_atomically(
        config_file,
        original_content,
        original_mode,
    )

    run_command([sysctl_path, "--system"])


def perform_sysctl_rollback(
    sysctl_keys: list[str],
) -> tuple[str, str]:
    """
    Mengembalikan parameter ICMP Redirect ke nilai default.

    - CANCELLED: file atau parameter konfigurasi tidak ditemukan.
    - SKIPPED: seluruh konfigurasi dan runtime sudah bernilai default.
    - SUCCESS: rollback berhasil diterapkan dan divalidasi.
    """
    if not sysctl_keys:
        raise ValueError("Daftar parameter sysctl tidak boleh kosong.")

    sysctl_path = shutil.which("sysctl")

    if not sysctl_path:
        raise RuntimeError("Executable sysctl tidak ditemukan.")

    config_file = Path(SYSCTL_CONF)

    if not config_file.is_file() or config_file.is_symlink():
        return (
            "CANCELLED",
            f"Berkas konfigurasi {config_file.name} tidak ditemukan "
            "atau bukan file biasa.",
        )

    original_content = config_file.read_bytes()
    original_mode = get_config_mode(config_file)

    existing_content = original_content.decode(
        "utf-8",
        errors="replace",
    )

    config_values = get_config_values(
        existing_content,
        sysctl_keys,
    )

    found_keys = [
        key for key, values in config_values.items() if values
    ]

    if not found_keys:
        return (
            "CANCELLED",
            f"Tidak ada parameter yang ditemukan di {config_file.name}.",
        )

    default_value = str(SYSCTL_DEFAULT_ACCEPT_REDIRECTS)

    # Periksa konfigurasi dan runtime sebelum rollback.
    runtime_values = {
        key: get_runtime_sysctl_value(key)
        for key in sysctl_keys
    }

    persistent_compliant = all(
        config_values[key]
        and all(value == default_value for value in config_values[key])
        for key in sysctl_keys
    )

    runtime_compliant = all(
        value == default_value
        for value in runtime_values.values()
    )

    if persistent_compliant and runtime_compliant:
        details = ", ".join(
            f"{key}={value}"
            for key, value in runtime_values.items()
        )

        return (
            "SKIPPED",
            f"Seluruh parameter sudah bernilai default "
            f"({default_value}): {details}",
        )

    try:
        new_content = build_rollback_config(
            content=existing_content,
            sysctl_keys=sysctl_keys,
            default_value=default_value,
        )

        write_config_atomically(
            config_file,
            new_content.encode("utf-8"),
            original_mode,
        )

        run_command([sysctl_path, "--system"])

        # Validasi seluruh nilai runtime.
        details = []

        for key in sysctl_keys:
            value = get_runtime_sysctl_value(key)

            if value != default_value:
                raise RuntimeError(
                    f"Validasi rollback gagal: {key}={value}, "
                    f"seharusnya {default_value}."
                )

            details.append(f"{key}={value}")

        return (
            "SUCCESS",
            f"Parameter berhasil dikembalikan ke nilai default "
            f"{default_value}: {', '.join(details)}",
        )

    except Exception as exc:
        try:
            restore_config(
                config_file,
                original_content,
                original_mode,
                sysctl_path,
            )
        except Exception as restore_exc:
            raise RuntimeError(
                f"{exc}. Pemulihan konfigurasi juga gagal: "
                f"{restore_exc}"
            ) from exc

        raise RuntimeError(
            f"{exc}. Konfigurasi sebelumnya berhasil dipulihkan."
        ) from exc
    

def main():
    task_vars = load_taskfile_vars(SCRIPT_DIR)

    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="rollback.json",
        catalog=task_vars.get("ID", "K17"),
        nama=task_vars.get("NAMA", "Penolakan ICMP Redirect"),
        kode_cis=task_vars.get("KODE_CIS", "3.3.5"),
        judul_cis=task_vars.get("JUDUL_CIS", "Ensure icmp redirects are not accepted"),
        versi_cis=task_vars.get("VERSI_CIS", "Ubuntu 24.04 LTS Benchmark v2.0.0"),
        regulasi=task_vars.get("REGULASI", "Pasal 35, Pasal 39"),
        kepatuhan=task_vars.get("KEPATUHAN", "UU PDP No. 27/2022"),
        log_type="rollback",
    )

    lock_name = CATALOG_LOCKS.get("K17", "accept_redirects_audit")
    lock_file = acquire_lock(lock_name, logger)

    start = perf_counter()

    try:
        status, detail = perform_sysctl_rollback(
            SYSCTL_KEYS_ACCEPT_REDIRECTS
        )

        if status == "SUCCESS":
            logger.log(
                LogStatus.SUCCESS, 
                "Result", 
                f"Hasil Rollback: SUCCESS - {detail}",
                duration_ms=(perf_counter() - start) * 1000,
            )
        elif status == "SKIPPED":
            logger.log(
                LogStatus.SKIPPED,
                "Result", 
                f"Hasil Rollback: SKIPPED - {detail}",
                duration_ms=(perf_counter() - start) * 1000,
            )
        else:
            logger.log(
                LogStatus.SKIPPED,
                "Result", 
                f"Hasil Rollback: CANCELLED - {detail}",
                duration_ms=(perf_counter() - start) * 1000,
            )
        
        sys.exit(0)

    except Exception as e:
        logger.log_error(
            "K17", 
            "rollback", 
            e,
            duration_ms=(perf_counter() - start) * 1000,
        )

    finally:
        release_lock(lock_file)


if __name__ == "__main__":
    main()