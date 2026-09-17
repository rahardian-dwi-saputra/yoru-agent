from __future__ import annotations
from pathlib import Path
import subprocess
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
JOURNAL_LOG_DIR = Path("/var/log/journal")


def apply_journald_storage_hardening(config_path: Path) -> bool:
    """Mengatur directive 'Storage=persistent' pada file journald.conf."""
    if not config_path.is_file():
        return False

    lines = []
    storage_found = False

    with open(config_path, "r", encoding="utf-8", errors="ignore") as f:
        for line in f:
            line_stripped = line.strip()

            # Jika menemukan baris Storage= (baik aktif maupun terkomentar)
            if line_stripped.lower().startswith("storage=") or (
                (line_stripped.startswith("#") or line_stripped.startswith(";"))
                and "storage=" in line_stripped.lower()
            ):
                if not storage_found:
                    lines.append("Storage=persistent\n")
                    storage_found = True
            else:
                lines.append(line)

    # Jika directive Storage= belum ada sama sekali di dalam file
    if not storage_found:
        lines.append("\nStorage=persistent\n")

    with open(config_path, "w", encoding="utf-8") as f:
        f.writelines(lines)

    return True


def restart_journald_service() -> bool:
    """Memuat ulang service systemd-journald agar konfigurasi baru aktif."""
    try:
        res = subprocess.run(
            ["systemctl", "restart", "systemd-journald"],
            capture_output=True,
            text=True,
        )
        return res.returncode == 0
    except Exception:
        return False


def main():
    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="hardening.json",
        catalog="K08",
        cis_id="6.1.2.4",
        log_type="hardening",
    )

    lock_file = acquire_lock("journald_storage_hardening", logger)

    try:
        if not JOURNALD_CONFIG.is_file():
            logger.log(
                "FAILED",
                "Result",
                f"Hasil Hardening: FAILED - Berkas konfigurasi {JOURNALD_CONFIG} tidak ditemukan.",
            )
            return

        # 1. Buat direktori /var/log/journal jika belum ada
        if not JOURNAL_LOG_DIR.is_dir():
            JOURNAL_LOG_DIR.mkdir(parents=True, exist_ok=True)
            logger.log(
                "SUCCESS",
                "Step",
                f"Direktori penyimpanan log {JOURNAL_LOG_DIR} berhasil dibuat.",
            )

        # 2. Terapkan konfigurasi Storage=persistent
        success = apply_journald_storage_hardening(JOURNALD_CONFIG)

        if not success:
            logger.log(
                "FAILED",
                "Result",
                "Hasil Hardening: FAILED - Gagal meng-update berkas konfigurasi journald.",
            )
            return

        # 3. Restart service systemd-journald
        if restart_journald_service():
            logger.log(
                "SUCCESS",
                "Result",
                "Hasil Hardening: SUCCESS - Parameter 'Storage=persistent' berhasil diterapkan dan service systemd-journald berhasil di-restart.",
            )
        else:
            logger.log(
                "FAILED",
                "Result",
                "Hasil Hardening: FAILED - Konfigurasi diperbarui tetapi gagal merestart service systemd-journald.",
            )

    except Exception as e:
        logger.log_error("K08", "hardening", e)

    finally:
        release_lock(lock_file)


if __name__ == "__main__":
    main()