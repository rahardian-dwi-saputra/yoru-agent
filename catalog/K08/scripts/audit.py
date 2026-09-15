from __future__ import annotations

import subprocess
import sys
from pathlib import Path

# Import modul catalogutils via sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]  # Naik 3 level ke yoru-agent/

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.catalogutils import BaseLogger


def is_ufw_installed() -> bool:
    """Memeriksa apakah paket UFW terinstall pada sistem Debian/Ubuntu."""
    try:
        res = subprocess.run(
            ["dpkg-query", "-s", "ufw"],
            capture_output=True,
            text=True,
        )
        return res.returncode == 0 and "Status: install ok installed" in res.stdout
    except Exception:
        return False


def main():
    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="audit.json",
        catalog="K08",
        cis_id="4.2.1",
        log_type="audit",
    )

    try:
        if is_ufw_installed():
            logger.log(
                "COMPLIANT",
                "Result",
                "Hasil Audit: COMPLIANT - Paket 'ufw' sudah terinstall pada sistem.",
            )
            sys.exit(0)
        else:
            logger.log(
                "NON_COMPLIANT",
                "Result",
                "Hasil Audit: NON_COMPLIANT - Paket 'ufw' belum terinstall pada sistem.",
            )
            sys.exit(0)

    except Exception as e:
        logger.log(
            "ERROR",
            "Note",
            f"Terjadi error saat melakukan audit K08: {e}",
        )
        logger.log(
            "FAILED",
            "Result",
            "Hasil Audit: FAILED - Terjadi kesalahan pada proses audit.",
        )
        sys.exit(1)


if __name__ == "__main__":
    main()