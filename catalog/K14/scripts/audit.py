from __future__ import annotations
from pathlib import Path
from typing import Dict
from time import perf_counter
import subprocess
import sys
import shutil

# Import modul catalogutils via sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]  # Naik 3 level ke yoru-agent/

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import (
    UFW_PACKAGE_NAME, 
    CATALOG_LOCKS
)

from pipeline.catalogutils import (
    LogStatus,
    BaseLogger,
    load_taskfile_vars,
    acquire_lock,
    release_lock,
    is_package_installed,
)



def get_ufw_default_policies() -> Dict[str, str]:
    """Mengambil kebijakan default UFW untuk incoming, outgoing, dan routed."""
    ufw_path = shutil.which("ufw")

    if not ufw_path:
        raise RuntimeError("Executable UFW tidak ditemukan.")

    try:
        result = subprocess.run(
            [ufw_path, "status", "verbose"],
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            "Proses pembacaan kebijakan default UFW mengalami timeout."
        ) from exc
    except OSError as exc:
        raise RuntimeError(
            f"Gagal menjalankan perintah UFW: {exc}"
        ) from exc

    if result.returncode != 0:
        error_message = result.stderr.strip() or "Tidak ada pesan error."
        raise RuntimeError(
            f"Gagal membaca status UFW: {error_message}"
        )

    policies = {
        "incoming": "",
        "outgoing": "",
        "routed": "",
    }

    for line in result.stdout.splitlines():
        line = line.strip()

        if not line.lower().startswith("default:"):
            continue

        entries = line.split(":", 1)[1].split(",")

        for entry in entries:
            entry = entry.strip().lower()

            for policy in policies:
                if f"({policy})" in entry:
                    value = entry.split("(", 1)[0].strip()

                    if value:
                        policies[policy] = value

        break

    missing = [
        policy
        for policy, value in policies.items()
        if not value
    ]

    if missing:
        raise RuntimeError(
            "Kebijakan default UFW tidak ditemukan atau tidak lengkap: "
            + ", ".join(missing)
        )

    return policies


def main():
    task_vars = load_taskfile_vars(SCRIPT_DIR)

    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="audit.json",
        catalog=task_vars.get("ID", "K14"),
        nama=task_vars.get("NAMA", "Pengaturan Kebijakan Default UFW Firewall (Deny By Default)"),
        kode_cis=task_vars.get("KODE_CIS", "4.2.7"),
        judul_cis=task_vars.get("JUDUL_CIS", "Ensure ufw default deny firewall policy"),
        versi_cis=task_vars.get("VERSI_CIS", "Ubuntu 24.04 LTS Benchmark v2.0.0"),
        regulasi=task_vars.get("REGULASI", "Pasal 35, Pasal 39"),
        kepatuhan=task_vars.get("KEPATUHAN", "UU PDP No. 27/2022"),
        log_type="audit",
    )

    lock_name = CATALOG_LOCKS.get("K14", "ufw_audit")
    lock_file = acquire_lock(lock_name, logger)

    start = perf_counter()

    try:
        if not is_package_installed(UFW_PACKAGE_NAME):
            logger.log(
                LogStatus.FAILED,
                "Result",
                f"Hasil Audit: FAILED - Paket '{UFW_PACKAGE_NAME}' belum terinstall pada sistem.",
                duration_ms=(perf_counter() - start) * 1000,
            )
            sys.exit(1)

        # Cek policy default UFW
        policies = get_ufw_default_policies()

        incoming = policies["incoming"]
        outgoing = policies["outgoing"]
        routed = policies["routed"]

        # Validasi kebijakan default UFW
        is_incoming_ok = incoming in ("deny", "reject")
        is_routed_ok = routed in ("deny", "reject", "disabled")

        if is_incoming_ok and is_routed_ok:
            logger.log(
                LogStatus.COMPLIANT,
                "Result",
                f"Hasil Audit: COMPLIANT - Kebijakan default UFW memenuhi baseline. (incoming: {incoming}, outgoing: {outgoing}, routed: {routed}).",
                duration_ms=(perf_counter() - start) * 1000,
            )
            sys.exit(0)
        else:
            logger.log(
                LogStatus.NON_COMPLIANT,
                "Result",
                f"Hasil Audit: NON_COMPLIANT - Kebijakan default UFW tidak memenuhi baseline. (incoming: {incoming}, outgoing: {outgoing}, routed: {routed}).",
                duration_ms=(perf_counter() - start) * 1000,
            )
            sys.exit(1)
    except Exception as e:
        logger.log_error(
            "K14", 
            "audit", 
            e,
            duration_ms=(perf_counter() - start) * 1000,
        )
        sys.exit(2)
    finally:
        release_lock(lock_file)


if __name__ == "__main__":
    main()