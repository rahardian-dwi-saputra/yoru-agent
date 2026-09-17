from __future__ import annotations
from pathlib import Path
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

def main():
    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="audit.json",
        catalog="K08",
        cis_id="4.2.1",
        log_type="audit",
    )

    lock_file = acquire_lock_ufw(logger)

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
        logger.log_error("K08", "audit", e)

    finally:
        release_lock(lock_file)


if __name__ == "__main__":
    main()