from __future__ import annotations
from pathlib import Path
from typing import Optional, Tuple
import glob
import sys

# Import modul catalogutils via sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]  # Naik 3 level ke yoru-agent/

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.catalogutils import (
    BaseLogger,
    acquire_lock,
    release_lock,
)

JOURNALD_CONFIG = Path("/etc/systemd/journald.conf")
JOURNALD_DROPIN_DIR = Path("/etc/systemd/journald.conf.d")
JOURNAL_LOG_DIR = Path("/var/log/journal")


def parse_journald_storage() -> Tuple[str, Optional[str]]:
    """Memeriksa dan meng-extract nilai directive 'Storage' dari journald.conf

    serta berkas drop-in di /etc/systemd/journald.conf.d/*.conf.

    Return:
        Tuple[state, value]
        - state: 'not_found', 'commented', 'active'
        - value: Nilai konfigurasi Storage (contoh: 'persistent', 'auto', dll)
    """
    config_files = []
    if JOURNALD_CONFIG.is_file():
        config_files.append(JOURNALD_CONFIG)

    if JOURNALD_DROPIN_DIR.is_dir():
        dropin_files = sorted(glob.glob(str(JOURNALD_DROPIN_DIR / "*.conf")))
        config_files.extend([Path(f) for f in dropin_files])

    if not config_files:
        return "not_found", None

    last_state = "not_found"
    last_value = None

    for config_path in config_files:
        try:
            with open(config_path, "r", encoding="utf-8", errors="ignore") as f:
                for line in f:
                    line_stripped = line.strip()

                    # 1. Baris Terkomentar (# atau ;)
                    if line_stripped.startswith("#") or line_stripped.startswith(";"):
                        uncommented = line_stripped[1:].lstrip()
                        if uncommented.lower().startswith("storage="):
                            parts = uncommented.split("=", 1)
                            if len(parts) == 2:
                                last_state = "commented"
                                last_value = parts[1].strip()

                    # 2. Baris Aktif
                    elif line_stripped.lower().startswith("storage="):
                        parts = line_stripped.split("=", 1)
                        if len(parts) == 2:
                            last_state = "active"
                            last_value = parts[1].strip()
        except Exception:
            continue

    return last_state, last_value


def main():
    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="audit.json",
        catalog="K08",
        cis_id="6.1.2.4",
        log_type="audit",
    )

    lock_file = acquire_lock("journald_storage_audit", logger)

    try:
        state, storage_val = parse_journald_storage()

        # Skenario 1: Parameter Storage tidak ditemukan sama sekali
        if state == "not_found":
            logger.log(
                "NON_COMPLIANT",
                "Result",
                "Hasil Audit: NON_COMPLIANT - Berkas konfigurasi journald tidak ditemukan.",
            )
            return

        # Skenario 2: Parameter Storage dikomentari / default (belum diatur eksplisit)
        if state == "commented" or not storage_val:
            logger.log(
                "NON_COMPLIANT",
                "Result",
                f"Hasil Audit: NON_COMPLIANT - Parameter 'Storage' belum dikonfigurasi secara eksplisit (State: {state}).",
            )
            return

        storage_val_lower = storage_val.lower()

        # Standar CIS: Storage harus bernilai 'persistent' atau 'auto'
        # Jika 'persistent', direktori /var/log/journal harus ada
        is_storage_ok = storage_val_lower in ("persistent", "auto")

        if is_storage_ok:
            if storage_val_lower == "persistent" and not JOURNAL_LOG_DIR.is_dir():
                logger.log(
                    "NON_COMPLIANT",
                    "Result",
                    f"Hasil Audit: NON_COMPLIANT - Parameter Storage diatur 'persistent', namun direktori {JOURNAL_LOG_DIR} belum dibuat.",
                )
            else:
                logger.log(
                    "COMPLIANT",
                    "Result",
                    f"Hasil Audit: COMPLIANT - Parameter 'Storage' journald telah dikonfigurasi dengan benar (Storage={storage_val}).",
                )
        else:
            logger.log(
                "NON_COMPLIANT",
                "Result",
                f"Hasil Audit: NON_COMPLIANT - Parameter 'Storage' diatur ke '{storage_val}' (Seharusnya 'persistent' atau 'auto').",
            )

    except Exception as e:
        logger.log_error("K08", "audit", e)

    finally:
        release_lock(lock_file)


if __name__ == "__main__":
    main()