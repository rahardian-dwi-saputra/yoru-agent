from __future__ import annotations
from pathlib import Path
from time import perf_counter
import sys
import shutil


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]  # Naik 3 level ke yoru-agent/

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import (
    SYSCTL_CONF,
    SYSCTL_KEY_ICMP_ECHO_BROADCASTS,
    SYSCTL_TARGET_ICMP_ECHO_BROADCASTS,
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
    get_persistent_sysctl_value,
    write_config_atomically,
)


def update_sysctl_config(
    sysctl_key: str,
    target_value: str,
    comment: str,
) -> tuple[str, bool]:
    """
    Memperbarui parameter sysctl tanpa mengubah konfigurasi lain.

    Mengganti seluruh deklarasi aktif parameter yang sama agar
    tidak terjadi konflik akibat duplikasi.
    """

    config_file = SYSCTL_CONF
    config_file.parent.mkdir(parents=True, exist_ok=True)

    if config_file.is_symlink():
        raise RuntimeError(
            f"File konfigurasi {config_file} merupakan symbolic link. "
            "Hardening dibatalkan demi keamanan."
        )

    if config_file.exists() and not config_file.is_file():
        raise RuntimeError(
            f"Path konfigurasi {config_file} bukan file reguler."
        )

    original_content = (
        config_file.read_bytes()
        if config_file.exists()
        else b""
    )

    original_mode = (
        config_file.stat().st_mode & 0o777
        if config_file.exists()
        else 0o644
    )

    try:
        content = original_content.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise RuntimeError(
            f"File konfigurasi {config_file} bukan teks UTF-8 yang valid."
        ) from exc

    lines = content.splitlines()
    updated_lines = []
    key_found = False

    for line in lines:
        stripped = line.strip()

        if not stripped or stripped.startswith("#") or "=" not in stripped:
            updated_lines.append(line)
            continue

        current_key, _ = stripped.split("=", 1)

        if current_key.strip().replace("/", ".") == sysctl_key:
            if not key_found:
                updated_lines.append(
                    f"{sysctl_key} = {target_value}"
                )
                key_found = True
            else:
                # Nonaktifkan deklarasi aktif yang duplikat.
                updated_lines.append(
                    f"# Disabled by Yoru-Agent: {line.strip()}"
                )
        else:
            updated_lines.append(line)

    if not key_found:
        if updated_lines and updated_lines[-1].strip():
            updated_lines.append("")

        updated_lines.extend([
            f"# {comment}",
            f"{sysctl_key} = {target_value}",
        ])

    updated_content = "\n".join(updated_lines) + "\n"

    if updated_content.encode("utf-8") == original_content:
        return "Konfigurasi sudah sesuai.", False

    write_config_atomically(
        config_file,
        updated_content,
        mode=0o644,
    )

    return "Konfigurasi berhasil diperbarui.", True


def restore_config(
    config_file: Path,
    original_content: bytes,
    original_mode: int,
    file_existed: bool,
) -> None:
    """Mengembalikan konfigurasi awal jika hardening gagal."""

    if file_existed:
        write_config_atomically(
            config_file,
            original_content,
            mode=original_mode,
        )
    elif config_file.exists():
        config_file.unlink()


def apply_sysctl_hardening(
    sysctl_key: str,
    target_value: str,
    comment: str,
) -> tuple[str, str]:
    """
    Menerapkan hardening sysctl.

    Status:
    - SUCCESS: Konfigurasi berhasil diterapkan.
    - SKIPPED: Runtime dan konfigurasi persisten sudah sesuai.
    - FAILED: Proses hardening gagal.
    """

    sysctl_path = shutil.which("sysctl")

    if not sysctl_path:
        return (
            "FAILED",
            "Executable sysctl tidak ditemukan.",
        )

    config_file = SYSCTL_CONF

    file_existed = config_file.exists()
    original_content = (
        config_file.read_bytes()
        if file_existed
        else b""
    )
    original_mode = (
        config_file.stat().st_mode & 0o777
        if file_existed
        else 0o644
    )

    try:
        # Periksa kondisi runtime.
        runtime_value = get_runtime_sysctl_value(sysctl_key)

        # Periksa konfigurasi persisten.
        persistent_value = get_persistent_sysctl_value(sysctl_key)

        # Lewati jika runtime dan persistent sudah sesuai.
        if (
            runtime_value == target_value
            and persistent_value == target_value
        ):
            return (
                "SKIPPED",
                (
                    f"Parameter {sysctl_key} sudah berada dalam "
                    f"kondisi hardening. Runtime: {runtime_value}, "
                    f"Persistent: {persistent_value}. "
                    "Tidak diperlukan perubahan konfigurasi."
                ),
            )

        # Perbarui konfigurasi persisten.
        detail, changed = update_sysctl_config(
            sysctl_key=sysctl_key,
            target_value=target_value,
            comment=comment,
        )

        # Terapkan konfigurasi.
        run_command(
            [sysctl_path, "--system"],
            timeout=60,
        )

        # Validasi runtime setelah penerapan.
        runtime_value = get_runtime_sysctl_value(sysctl_key)

        if runtime_value != target_value:
            raise RuntimeError(
                f"Validasi runtime gagal. "
                f"Nilai aktual: {runtime_value}, "
                f"nilai yang diharapkan: {target_value}."
            )

        return (
            "SUCCESS",
            (
                f"{detail} Parameter {sysctl_key} = {target_value} "
                f"berhasil diterapkan dan diverifikasi. "
                f"Perubahan konfigurasi: "
                f"{'Ya' if changed else 'Tidak'}."
            ),
        )

    except Exception as exc:
        rollback_message = ""

        try:
            restore_config(
                config_file=config_file,
                original_content=original_content,
                original_mode=original_mode,
                file_existed=file_existed,
            )

            run_command(
                [sysctl_path, "--system"],
                timeout=60,
            )

            rollback_message = (
                " Konfigurasi awal berhasil dipulihkan."
            )

        except Exception as rollback_exc:
            rollback_message = (
                f" PERINGATAN: Pemulihan konfigurasi gagal: "
                f"{rollback_exc}"
            )

        return (
            "FAILED",
            f"Gagal menerapkan hardening sysctl: {exc}."
            f"{rollback_message}",
        )


def main():
    task_vars = load_taskfile_vars(SCRIPT_DIR)

    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="hardening.json",
        catalog=task_vars.get("ID", "K16"),
        nama=task_vars.get("NAMA", "Pengabaian Permintaan ICMP Broadcast"),
        kode_cis=task_vars.get("KODE_CIS", "3.3.4"),
        judul_cis=task_vars.get("JUDUL_CIS", "Ensure broadcast icmp requests are ignored"),
        versi_cis=task_vars.get("VERSI_CIS", "Ubuntu 24.04 LTS Benchmark v2.0.0"),
        regulasi=task_vars.get("REGULASI", "Pasal 35, Pasal 39"),
        kepatuhan=task_vars.get("KEPATUHAN", "UU PDP No. 27/2022"),
        log_type="hardening",
    )

    lock_name = CATALOG_LOCKS.get("K16", "icmp_broadcast_audit")
    lock_file = acquire_lock(lock_name, logger)

    start = perf_counter()

    try:
        status, detail = apply_sysctl_hardening(
            sysctl_key=SYSCTL_KEY_ICMP_ECHO_BROADCASTS,
            target_value=str(SYSCTL_TARGET_ICMP_ECHO_BROADCASTS),
            comment="CIS 3.3.4: Ensure broadcast icmp requests are ignored",
        )

        if status == "SKIPPED":
            logger.log(
                LogStatus.SKIPPED,
                "Result",
                f"Hasil Hardening: SKIPPED - {detail}",
                duration_ms=(perf_counter() - start) * 1000,
            )
            sys.exit(0)
        elif status == "SUCCESS":
            logger.log(
                LogStatus.SUCCESS,
                "Result",
                f"Hasil Hardening: SUCCEED - {detail}",
                duration_ms=(perf_counter() - start) * 1000,
            )
            sys.exit(0)
        else:
            logger.log(
                LogStatus.FAILED,
                "Result",
                f"Hasil Hardening: FAILED - {detail}",
                duration_ms=(perf_counter() - start) * 1000,
            )
            sys.exit(1)

    except Exception as e:
        logger.log_error(
            "K16", 
            "hardening", 
            e,
            duration_ms=(perf_counter() - start) * 1000,
        )
        sys.exit(2)
    finally:
        release_lock(lock_file)


if __name__ == "__main__":
    main()