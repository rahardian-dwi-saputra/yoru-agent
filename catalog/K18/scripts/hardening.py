from __future__ import annotations
from pathlib import Path
from time import perf_counter
import sys
import shutil


# Import modul catalogutils via sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]  # Naik 3 level ke yoru-agent/

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import (
    SYSCTL_CONF,
    SYSCTL_KEYS_ACCEPT_SOURCE_ROUTE,
    SYSCTL_TARGET_ACCEPT_SOURCE_ROUTE,
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
    get_config_mode,
    restore_config
)


def build_sysctl_config(
    existing_content: str,
    sysctl_keys: list[str],
    target_value: str,
    comment: str,
) -> str:
    """Memperbarui atau menambahkan parameter sysctl."""
    processed_keys = set()
    new_lines = []

    for line in existing_content.splitlines(keepends=True):
        stripped = line.strip()

        if stripped and not stripped.startswith("#") and "=" in stripped:
            current_key, _, _ = stripped.partition("=")
            current_key = current_key.strip()

            if current_key in sysctl_keys:
                new_lines.append(f"{current_key} = {target_value}\n")
                processed_keys.add(current_key)
                continue

        new_lines.append(line)

    missing_keys = [
        key for key in sysctl_keys if key not in processed_keys
    ]

    if missing_keys:
        if new_lines and not new_lines[-1].endswith("\n"):
            new_lines.append("\n")

        if not existing_content:
            new_lines.append(f"# {comment}\n")
        elif new_lines and new_lines[-1].strip():
            new_lines.append("\n")

        for key in missing_keys:
            new_lines.append(f"{key} = {target_value}\n")

    return "".join(new_lines)


def is_config_compliant(
    config_content: str,
    sysctl_keys: list[str],
    target_value: str,
) -> bool:
    """Memeriksa nilai parameter dalam file konfigurasi."""
    values = {key: [] for key in sysctl_keys}

    for line in config_content.splitlines():
        stripped = line.strip()

        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue

        key, _, value = stripped.partition("=")
        key = key.strip()

        if key in values:
            values[key].append(value.strip())

    return all(
        values[key] and all(value == target_value for value in values[key])
        for key in sysctl_keys
    )


def apply_sysctl_hardening_list(
    sysctl_keys: list[str],
    target_value: str,
    comment: str,
) -> tuple[str, str]:
    """
    Menerapkan hardening Penolakan Source Routed Packets.

    Memperbarui konfigurasi persisten, menerapkan sysctl,
    dan memvalidasi nilai runtime.
    """

    if not sysctl_keys:
        raise ValueError("Daftar parameter sysctl tidak boleh kosong.")

    sysctl_path = shutil.which("sysctl")

    if not sysctl_path:
        raise RuntimeError("Executable sysctl tidak ditemukan.")

    config_file = Path(SYSCTL_CONF)
    original_content = None
    original_mode = get_config_mode(config_file)

    if config_file.exists():
        original_content = config_file.read_bytes()
        existing_content = original_content.decode(
            "utf-8",
            errors="replace",
        )
    else:
        existing_content = ""

    target_value = str(target_value)

    # Periksa konfigurasi persisten dan runtime.
    runtime_compliant = all(
        get_runtime_sysctl_value(key) == target_value
        for key in sysctl_keys
    )

    persistent_compliant = is_config_compliant(
        existing_content,
        sysctl_keys,
        target_value,
    )

    if runtime_compliant and persistent_compliant:
        return (
            "SKIPPED",
            "Semua parameter paket source routed sudah sesuai target "
            "pada konfigurasi dan runtime.",
        )

    try:
        new_content = build_sysctl_config(
            existing_content=existing_content,
            sysctl_keys=sysctl_keys,
            target_value=target_value,
            comment=comment,
        )

        write_config_atomically(
            config_file,
            new_content.encode("utf-8"),
            original_mode,
        )

        run_command([sysctl_path, "--system"])

        # Validasi nilai runtime setelah penerapan.
        details = []

        for key in sysctl_keys:
            value = get_runtime_sysctl_value(key)

            if value != target_value:
                raise RuntimeError(
                    f"Validasi gagal: {key}={value}, "
                    f"seharusnya {target_value}."
                )

            details.append(f"{key}={value}")

        return (
            "SUCCESS",
            "Hardening paket source routed berhasil diterapkan: "
            + ", ".join(details),
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
                f"{exc}. Pemulihan konfigurasi juga gagal: {restore_exc}"
            ) from exc

        raise RuntimeError(
            f"{exc}. Konfigurasi sebelumnya berhasil dipulihkan."
        ) from exc


def main():
    task_vars = load_taskfile_vars(SCRIPT_DIR)

    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="hardening.json",
        catalog=task_vars.get("ID", "K18"),
        nama=task_vars.get("NAMA", "Penolakan Source Routed Packets"),
        kode_cis=task_vars.get("KODE_CIS", "3.3.8"),
        judul_cis=task_vars.get("JUDUL_CIS", "Ensure source routed packets are not accepted"),
        versi_cis=task_vars.get("VERSI_CIS", "Ubuntu 24.04 LTS Benchmark v2.0.0"),
        regulasi=task_vars.get("REGULASI", "Pasal 35, Pasal 39"),
        kepatuhan=task_vars.get("KEPATUHAN", "UU PDP No. 27/2022"),
        log_type="hardening",
    )

    lock_name = CATALOG_LOCKS.get("K18", "source_route_hardening")
    lock_file = acquire_lock(lock_name, logger)

    start = perf_counter()

    try:
        status, detail = apply_sysctl_hardening_list(
            sysctl_keys=SYSCTL_KEYS_ACCEPT_SOURCE_ROUTE,
            target_value=SYSCTL_TARGET_ACCEPT_SOURCE_ROUTE,
            comment="CIS 3.3.8 Ensure source routed packets are not accepted",
        )

        if status == "SUCCESS":
            logger.log(
                LogStatus.SUCCESS,
                "Result",
                f"Hasil Hardening: SUCCESS - {detail}",
                duration_ms=(perf_counter() - start) * 1000,
            )
        else:
            logger.log(
                LogStatus.SKIPPED,
                "Result",
                f"Hasil Hardening: SKIPPED - {detail}",
                duration_ms=(perf_counter() - start) * 1000,
            )

        sys.exit(0)

    except Exception as e:
        logger.log_error(
            "K18", 
            "hardening", 
            e,
            duration_ms=(perf_counter() - start) * 1000,
        )
        sys.exit(1)
    finally:
        release_lock(lock_file)


if __name__ == "__main__":
    main()