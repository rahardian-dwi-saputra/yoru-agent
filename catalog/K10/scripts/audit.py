from __future__ import annotations
from pathlib import Path
from typing import Dict
import subprocess
import sys


# Import modul catalogutils via sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]  # Naik 3 level ke yoru-agent/

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.catalogutils import (
    BaseLogger,
    acquire_lock_ufw,
    is_ufw_installed,
    release_lock
)


def get_ufw_default_policies() -> Dict[str, str]:
    """Mengambil status kebijakan default UFW (incoming, outgoing, routed)."""
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
                    # Contoh format output: Default: deny (incoming), allow (outgoing), disabled (routed)
                    # atau: Default: deny (incoming), allow (outgoing), deny (routed)
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


def main():
    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="audit.json",
        catalog="K10",
        cis_id="4.2.7",
        log_type="audit",
    )

    lock_file = acquire_lock_ufw(logger)

    try:
        if not is_ufw_installed():
            logger.log(
                "FAILED",
                "Result",
                "Hasil Audit: FAILED - Paket 'ufw' belum terinstall pada sistem.",
            )
            sys.exit(0)

        # Cek policy default UFW
        policies = get_ufw_default_policies()

        incoming = policies.get("incoming", "")
        routed = policies.get("routed", "")

        # Kebijakan CIS: incoming harus deny/reject, routed harus deny/reject/disabled
        is_incoming_ok = incoming in ("deny", "reject")
        is_routed_ok = routed in ("deny", "reject", "disabled")

        if is_incoming_ok and is_routed_ok:
            logger.log(
                "COMPLIANT",
                "Result",
                f"Hasil Audit: COMPLIANT - Kebijakan default UFW sudah aman (incoming: {incoming}, routed: {routed}).",
            )
        else:
            logger.log(
                "NON_COMPLIANT",
                "Result",
                f"Hasil Audit: NON_COMPLIANT - Kebijakan default UFW tidak aman (incoming: {incoming}, routed: {routed}).",
            )

    except Exception as e:
        logger.log_error("K10", "audit", e)

    finally:
        release_lock(lock_file)


if __name__ == "__main__":
    main()