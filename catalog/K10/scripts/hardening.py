from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Dict

# Import modul catalogutils via sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]  # Naik 3 level ke yoru-agent/

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.catalogutils import BaseLogger, acquire_lock, release_lock

STATE_FILE = SCRIPT_DIR.parent / "state_k10.json"


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


def get_ufw_default_policies() -> Dict[str, str]:
    """Mengambil status kebijakan default UFW saat ini."""
    policies = {"incoming": "", "outgoing": "", "routed": ""}
    try:
        res = subprocess.run(
            ["ufw", "status", "verbose"],
            capture_output=True,
            text=True,
        )
        if res.returncode == 0:
            for line in res.stdout.splitlines():
                line_lower = line.strip().lower()
                if "default:" in line_lower:
                    parts = line_lower.replace("default:", "").split(",")
                    for part in parts:
                        part = part.strip()
                        if "(incoming)" in part:
                            policies["incoming"] = part.split()[0]
                        elif "(outgoing)" in part:
                            policies["outgoing"] = part.split()[0]
                        elif "(routed)" in part:
                            policies["routed"] = part.split()[0]
    except Exception:
        pass

    return policies


def apply_default_policies() -> bool:
    """Menerapkan kebijakan default deny pada incoming dan routed UFW."""
    try:
        # Default deny incoming
        res_in = subprocess.run(
            ["ufw", "default", "deny", "incoming"],
            capture_output=True,
            text=True,
        )

        # Default deny routed
        res_route = subprocess.run(
            ["ufw", "default", "deny", "routed"],
            capture_output=True,
            text=True,
        )

        return res_in.returncode == 0 and res_route.returncode == 0
    except Exception:
        return False


def main():
    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="hardening.json",
        catalog="K10",
        cis_id="4.2.7",
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

        # 2. Cek status kebijakan default saat ini
        current_policies = get_ufw_default_policies()
        incoming = current_policies.get("incoming", "")
        routed = current_policies.get("routed", "")

        is_incoming_ok = incoming in ("deny", "reject")
        is_routed_ok = routed in ("deny", "reject", "disabled")

        if is_incoming_ok and is_routed_ok:
            logger.log(
                "INFO",
                "Result",
                "Hasil Hardening: CANCELLED - Kebijakan default UFW sudah sesuai standar CIS (deny/reject).",
            )
            sys.exit(0)

        # 3. Simpan state kondisi sebelum hardening (untuk keperluan rollback)
        state_data = {
            "previous_incoming": incoming if incoming else "allow",
            "previous_routed": routed if routed else "allow",
        }
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state_data, f, indent=2)

        # 4. Terapkan hardening
        if apply_default_policies():
            logger.log(
                "SUCCESS",
                "Result",
                "Hasil Hardening: SUCCEED - Kebijakan default UFW berhasil diubah ke 'deny incoming' dan 'deny routed'.",
            )
            sys.exit(0)
        else:
            logger.log(
                "FAILED",
                "Result",
                "Hasil Hardening: FAILED - Gagal memperbarui kebijakan default UFW.",
            )
            sys.exit(1)

    except Exception as e:
        logger.log(
            "ERROR",
            "Note",
            f"Terjadi error saat hardening K10: {e}",
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