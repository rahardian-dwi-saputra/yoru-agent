from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Import modul catalogutils via sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]  # Naik 3 level ke yoru-agent/

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.catalogutils import BaseLogger, acquire_lock, release_lock

STATE_FILE = SCRIPT_DIR.parent / "state_k09.txt"


def is_ufw_installed() -> bool:
    """Memeriksa apakah paket UFW terinstall pada sistem."""
    try:
        res = subprocess.run(
            ["dpkg-query", "-s", "ufw"],
            capture_output=True,
            text=True,
        )
        return res.returncode == 0 and "Status: install ok installed" in res.stdout
    except Exception:
        return False


def is_ufw_enabled_and_active() -> tuple[bool, bool]:
    """Mengecek apakah ufw service enabled (systemctl) dan aktif (ufw status)."""
    is_enabled = False
    is_active = False

    try:
        res_enabled = subprocess.run(
            ["systemctl", "is-enabled", "ufw"],
            capture_output=True,
            text=True,
        )
        is_enabled = res_enabled.stdout.strip() == "enabled"
    except Exception:
        is_enabled = False

    try:
        res_status = subprocess.run(
            ["ufw", "status"],
            capture_output=True,
            text=True,
        )
        is_active = "Status: active" in res_status.stdout
    except Exception:
        is_active = False

    return is_enabled, is_active


def enable_ufw_service() -> bool:
    """Mengaktifkan (enable) systemd service dan ufw firewall."""
    try:
        # Unmask ufw jika dalam posisi masked
        subprocess.run(["systemctl", "unmask", "ufw"], capture_output=True)

        # Enable systemd service
        res_systemd = subprocess.run(
            ["systemctl", "enable", "--now", "ufw"],
            capture_output=True,
            text=True,
        )

        # Jalankan 'ufw --force enable' untuk memastikan ruleset aktif
        res_ufw = subprocess.run(
            ["ufw", "--force", "enable"],
            capture_output=True,
            text=True,
        )

        return res_systemd.returncode == 0 and res_ufw.returncode == 0
    except Exception:
        return False


def main():
    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="hardening.json",
        catalog="K09",
        cis_id="4.2.3",
        log_type="hardening",
    )

    lock_file_obj = acquire_lock(logger)

    try:
        # 1. Cek prasyarat keberadaan UFW
        if not is_ufw_installed():
            logger.log(
                "FAILED",
                "Result",
                "Hasil Hardening: FAILED - Paket 'ufw' belum terinstall. Jalankan K08 terlebih dahulu.",
            )
            sys.exit(1)

        # 2. Cek status UFW saat ini
        is_enabled, is_active = is_ufw_enabled_and_active()

        if is_enabled and is_active:
            logger.log(
                "INFO",
                "Result",
                "Hasil Hardening: CANCELLED - Layanan 'ufw' sudah aktif dan enabled sebelumnya.",
            )
            sys.exit(0)

        # 3. Eksekusi Hardening
        if enable_ufw_service():
            # Catat state kondisi awal sebelum di-enable
            with open(STATE_FILE, "w", encoding="utf-8") as f:
                f.write(
                    f"previous_enabled={is_enabled}\nprevious_active={is_active}\n"
                )

            logger.log(
                "SUCCESS",
                "Result",
                "Hasil Hardening: SUCCEED - Layanan 'ufw' berhasil diaktifkan dan di-enable.",
            )
            sys.exit(0)
        else:
            logger.log(
                "FAILED",
                "Result",
                "Hasil Hardening: FAILED - Gagal mengaktifkan layanan 'ufw'.",
            )
            sys.exit(1)

    except Exception as e:
        logger.log(
            "ERROR",
            "Note",
            f"Terjadi error saat hardening K09: {e}",
        )
        logger.log(
            "FAILED",
            "Result",
            "Hasil Hardening: FAILED - Terjadi kesalahan pada proses hardening.",
        )
        sys.exit(1)

    finally:
        release_lock(lock_file_obj)


if __name__ == "__main__":
    main()