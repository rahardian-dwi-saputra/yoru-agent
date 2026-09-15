from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

# Import modul catalogutils via sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]  # Naik 3 level ke yoru-agent/

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.catalogutils import BaseLogger, acquire_lock, release_lock

STATE_FILE = SCRIPT_DIR.parent / "state_k10.json"


def restore_default_policies(prev_incoming: str, prev_routed: str) -> bool:
    """Mengembalikan kebijakan default UFW ke nilai sebelumnya."""
    try:
        success = True

        if prev_incoming:
            res_in = subprocess.run(
                ["ufw", "default", prev_incoming, "incoming"],
                capture_output=True,
                text=True,
            )
            if res_in.returncode != 0:
                success = False

        if prev_routed:
            res_route = subprocess.run(
                ["ufw", "default", prev_routed, "routed"],
                capture_output=True,
                text=True,
            )
            if res_route.returncode != 0:
                success = False

        return success
    except Exception:
        return False


def main():
    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="rollback.json",
        catalog="K10",
        cis_id="4.2.7",
        log_type="rollback",
    )

    lock_file_obj = acquire_lock(logger)

    try:
        # 1. Cek ketersediaan file state_k10.json
        if not STATE_FILE.is_file():
            logger.log(
                "INFO",
                "Result",
                "Hasil Rollback: CANCELLED - Tidak ada data perubahan yang dicatat oleh hardening K10 (state_k10.json tidak ditemukan).",
            )
            sys.exit(0)

        # 2. Baca state sebelumnya
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            state_data = json.load(f)

        prev_incoming = state_data.get("previous_incoming", "allow")
        prev_routed = state_data.get("previous_routed", "allow")

        # 3. Eksekusi rollback
        if restore_default_policies(prev_incoming, prev_routed):
            if STATE_FILE.exists():
                STATE_FILE.unlink()

            logger.log(
                "SUCCESS",
                "Result",
                f"Hasil Rollback: SUCCEED - Kebijakan default UFW berhasil dikembalikan (incoming: {prev_incoming}, routed: {prev_routed}).",
            )
            sys.exit(0)
        else:
            logger.log(
                "FAILED",
                "Result",
                "Hasil Rollback: FAILED - Gagal mengembalikan kebijakan default UFW.",
            )
            sys.exit(1)

    except Exception as e:
        logger.log(
            "ERROR",
            "Note",
            f"Terjadi error saat rollback K10: {e}",
        )
        logger.log(
            "FAILED",
            "Result",
            "Hasil Rollback: FAILED - Terjadi kesalahan pada proses rollback.",
        )
        sys.exit(1)

    finally:
        release_lock(lock_file_obj)


if __name__ == "__main__":
    main()