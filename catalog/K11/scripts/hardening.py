from __future__ import annotations
from pathlib import Path
from time import perf_counter
import base64
import json
import sys
import os
import tempfile

# Import modul catalogutils via sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]  # Naik 3 level ke yoru-agent/

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import (
    JOURNALD_CONFIG, 
    JOURNALD_BACKUP_DIR, 
    JOURNALD_ROTATION_BASELINE,
    JOURNALD_SERVICE_NAME,
    CATALOG_LOCKS
)

from pipeline.catalogutils import (
    LogStatus,
    BaseLogger,
    load_taskfile_vars,
    acquire_lock,
    release_lock,
    get_effective_journald_parameter,
    restart_system_service
)

BACKUP_FILE = JOURNALD_BACKUP_DIR / "journald-rotation.json"

def normalize_value(value: str) -> str:
    """Menormalisasi nilai konfigurasi untuk perbandingan."""
    return "".join(value.split()).lower()


def atomic_write(
    target: Path,
    content: bytes,
    mode: int = 0o600,
) -> None:
    """Menulis file secara atomik."""
    target.parent.mkdir(parents=True, exist_ok=True)

    temp_path = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=target.parent,
            prefix=f".{target.name}.",
            delete=False,
        ) as temp_file:
            temp_path = Path(temp_file.name)
            temp_file.write(content)
            temp_file.flush()
            os.fsync(temp_file.fileno())

        os.chmod(temp_path, mode)
        os.replace(temp_path, target)

    finally:
        if temp_path and temp_path.exists():
            temp_path.unlink()


def check_compliance() -> tuple[bool, list[str]]:
    """
    Memeriksa konfigurasi efektif journald terhadap baseline.

    Returns:
        tuple:
            - True jika seluruh parameter sesuai.
            - False jika terdapat parameter yang tidak sesuai.
            - Daftar hasil pemeriksaan setiap parameter.

    Jika konfigurasi gagal dibaca, exception diteruskan
    agar tidak dianggap sebagai kondisi non-compliant biasa.
    """
    results: list[str] = []
    compliant = True

    for parameter, expected_value in JOURNALD_ROTATION_BASELINE.items():
        try:
            actual_value = get_effective_journald_parameter(parameter)

        except RuntimeError as exc:
            compliant = False
            results.append(
                f"{parameter}: gagal diperiksa ({exc})"
            )
            continue

        if normalize_value(actual_value) != normalize_value(expected_value):
            compliant = False
            results.append(
                f"{parameter}: tidak sesuai "
                f"(aktual: {actual_value}, baseline: {expected_value})"
            )
        else:
            results.append(
                f"{parameter}: sesuai ({actual_value})"
            )

    return compliant, results


def create_backup() -> None:
    """
    Membuat backup konfigurasi drop-in sebelum hardening.

    Backup mencakup:
    - Status keberadaan file.
    - Isi konfigurasi.
    - Permission.
    - UID dan GID.
    """
    JOURNALD_BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    os.chmod(JOURNALD_BACKUP_DIR, 0o700)

    if JOURNALD_CONFIG.is_symlink():
        raise RuntimeError(
            f"File konfigurasi tidak boleh berupa symbolic link: "
            f"{JOURNALD_CONFIG}"
        )

    exists = JOURNALD_CONFIG.exists()

    backup_data = {
        "version": 1,
        "catalog": "K11",
        "config_file": str(JOURNALD_CONFIG),
        "exists": exists,
    }

    if exists:
        if not JOURNALD_CONFIG.is_file():
            raise RuntimeError(
                f"Target konfigurasi bukan file reguler: {JOURNALD_CONFIG}"
            )

        metadata = JOURNALD_CONFIG.stat()

        backup_data.update({
            "content": base64.b64encode(
                JOURNALD_CONFIG.read_bytes()
            ).decode("ascii"),
            "mode": metadata.st_mode & 0o7777,
            "uid": metadata.st_uid,
            "gid": metadata.st_gid,
        })

    backup_content = json.dumps(
        backup_data,
        indent=4,
    ).encode("utf-8")

    atomic_write(
        BACKUP_FILE,
        backup_content,
        mode=0o600,
    )


def restore_backup() -> None:
    """Mengembalikan konfigurasi drop-in dari backup."""
    if not BACKUP_FILE.is_file():
        raise RuntimeError(
            f"File backup tidak ditemukan: {BACKUP_FILE}"
        )

    try:
        backup_data = json.loads(
            BACKUP_FILE.read_text(encoding="utf-8")
        )
    except (json.JSONDecodeError, OSError) as exc:
        raise RuntimeError(
            f"Backup tidak dapat dibaca: {exc}"
        ) from exc

    if (
        not isinstance(backup_data, dict)
        or type(backup_data.get("version")) is not int
        or backup_data["version"] != 1
        or backup_data.get("catalog") != "K11"
        or backup_data.get("config_file") != str(JOURNALD_CONFIG)
        or type(backup_data.get("exists")) is not bool
    ):
        raise RuntimeError("Struktur backup K11 tidak valid.")

    if JOURNALD_CONFIG.is_symlink():
        raise RuntimeError(
            "Target konfigurasi merupakan symbolic link."
        )

    # File sebelumnya belum tersedia.
    if not backup_data["exists"]:
        if JOURNALD_CONFIG.exists():
            JOURNALD_CONFIG.unlink()
        return

    try:
        content = base64.b64decode(
            backup_data["content"],
            validate=True,
        )

        mode = backup_data["mode"]
        uid = backup_data["uid"]
        gid = backup_data["gid"]

        if (
            type(mode) is not int
            or type(uid) is not int
            or type(gid) is not int
            or not 0 <= mode <= 0o7777
            or uid < 0
            or gid < 0
        ):
            raise ValueError("Metadata backup tidak valid.")

    except (KeyError, ValueError, TypeError) as exc:
        raise RuntimeError(
            f"Data backup tidak valid: {exc}"
        ) from exc

    atomic_write(
        JOURNALD_CONFIG,
        content,
        mode=mode,
    )

    os.chown(JOURNALD_CONFIG, uid, gid)


def write_rotation_configuration() -> None:
    """Menerapkan konfigurasi rotasi log journald."""
    JOURNALD_CONFIG.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    if JOURNALD_CONFIG.is_symlink():
        raise RuntimeError(
            f"File konfigurasi tidak boleh berupa symbolic link: "
            f"{JOURNALD_CONFIG}"
        )

    lines = [
        "# Managed by Yoru-Agent - K11",
        "# journald log file rotation configuration",
        "",
        "[Journal]",
    ]

    for parameter, value in JOURNALD_ROTATION_BASELINE.items():
        lines.append(f"{parameter}={value}")

    content = "\n".join(lines) + "\n"

    atomic_write(
        JOURNALD_CONFIG,
        content.encode("utf-8"),
        mode=0o644,
    )

    os.chown(JOURNALD_CONFIG, 0, 0)


def validate_configuration() -> None:
    """Memastikan konfigurasi efektif sesuai baseline."""
    compliant, results = check_compliance()

    if not compliant:
        raise RuntimeError(
            "Validasi konfigurasi journald gagal:\n"
            + "\n".join(f"- {result}" for result in results)
        )


def main():
    task_vars = load_taskfile_vars(SCRIPT_DIR)

    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="hardening.json",
        catalog=task_vars.get("ID", "K11"),
        nama=task_vars.get("NAMA", "Konfigurasi Rotasi File Log Journald"),
        kode_cis=task_vars.get("KODE_CIS", "6.1.1.3"),
        judul_cis=task_vars.get("JUDUL_CIS", "Ensure journald log file rotation is configured"),
        versi_cis=task_vars.get("VERSI_CIS", "Ubuntu 24.04 LTS Benchmark v2.0.0"),
        regulasi=task_vars.get("REGULASI", "Pasal 31, Pasal 35"),
        kepatuhan=task_vars.get("KEPATUHAN", "UU PDP No. 27/2022"),
        log_type="hardening",
    )

    lock_name = CATALOG_LOCKS.get("K11", "journald_audit")
    lock_file = acquire_lock(lock_name, logger)

    start = perf_counter()

    try:

        # Periksa apakah konfigurasi sudah sesuai.
        compliant, results = check_compliance()

        if compliant:
            logger.log(
                LogStatus.SKIPPED,
                "Result",
                (
                    "Hasil Hardening: SKIPPED - "
                    "Konfigurasi rotasi file log journald "
                    "sudah sesuai baseline.\n"
                    + "\n".join(f"- {result}" for result in results)
                ),
                duration_ms=(perf_counter() - start) * 1000,
            )
            sys.exit(0)

        # Backup konfigurasi sebelum perubahan.
        create_backup()
        backup_created = True

        # Terapkan konfigurasi rotasi.
        write_rotation_configuration()

        # Validasi konfigurasi sebelum restart.
        validate_configuration()

        # Restart layanan journald.
        if not restart_system_service(JOURNALD_SERVICE_NAME):
            raise RuntimeError(
                f"Gagal merestart service {JOURNALD_SERVICE_NAME}."
            )

        # Validasi ulang setelah restart.
        validate_configuration()

        logger.log(
            LogStatus.SUCCESS,
            "Result",
            (
                "Hasil Hardening: SUCCEED - "
                "Konfigurasi rotasi file log journald "
                "berhasil diterapkan dan divalidasi."
            ),
            duration_ms=(perf_counter() - start) * 1000,
        )

        return 0

    except Exception as e:
        # Pulihkan konfigurasi jika backup sudah dibuat.
        if backup_created:
            try:
                restore_backup()

                if not restart_system_service(JOURNALD_SERVICE_NAME):
                    raise RuntimeError(
                        "Gagal merestart journald setelah pemulihan konfigurasi."
                    )

            except Exception as rollback_exc:
                logger.log_error(
                    "K11",
                    "rollback",
                    RuntimeError(
                        "Pemulihan otomatis konfigurasi K11 gagal: "
                        f"{rollback_exc}"
                    ),
                )

        logger.log_error(
            "K11", 
            "hardening", 
            e,
            duration_ms=(perf_counter() - start) * 1000,
        )
        sys.exit(2)
        
    finally:
        release_lock(lock_file)


if __name__ == "__main__":
    main()