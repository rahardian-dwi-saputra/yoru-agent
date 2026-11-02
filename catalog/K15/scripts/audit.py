from __future__ import annotations
from pathlib import Path
from typing import List, Dict, Any
from time import perf_counter
import ipaddress
import re
import shutil
import subprocess
import sys


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import APPROVED_SERVICES_SET, CATALOG_LOCKS

from pipeline.catalogutils import (
    LogStatus,
    BaseLogger,
    load_taskfile_vars,
    acquire_lock,
    release_lock
)


def get_listening_services() -> List[Dict[str, Any]]:
    """Mengambil daftar TCP/UDP socket yang sedang listening."""

    services = []
    errors = []

    # Prioritaskan ss
    ss_path = shutil.which("ss")

    if ss_path:
        try:
            result = subprocess.run(
                [ss_path, "-H", "-tulnp"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )

            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    parts = line.split(None, 6)

                    if len(parts) < 6:
                        continue

                    services.append({
                        "proto": parts[0].lower(),
                        "address": parts[4],
                        "process": parts[6] if len(parts) >= 7 else "",
                    })

                return services

            errors.append(
                f"ss gagal: {result.stderr.strip() or 'Tidak ada pesan error.'}"
            )

        except subprocess.TimeoutExpired:
            errors.append("Perintah ss mengalami timeout.")
        except OSError as exc:
            errors.append(f"Gagal menjalankan ss: {exc}")

    # Fallback ke netstat
    netstat_path = shutil.which("netstat")

    if netstat_path:
        try:
            result = subprocess.run(
                [netstat_path, "-tulnp"],
                capture_output=True,
                text=True,
                timeout=15,
                check=False,
            )

            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    parts = line.split()

                    if len(parts) < 6:
                        continue

                    proto = parts[0].lower()

                    # TCP hanya mengambil socket dengan status LISTEN.
                    # UDP tidak memiliki status LISTEN pada netstat.
                    if proto.startswith("tcp"):
                        if len(parts) < 7 or parts[5].upper() != "LISTEN":
                            continue

                        local_addr = parts[3]
                        process_info = parts[6]

                    elif proto.startswith("udp"):
                        local_addr = parts[3]
                        process_info = parts[5] if len(parts) >= 6 else ""

                    else:
                        continue

                    services.append({
                        "proto": proto,
                        "address": local_addr,
                        "process": process_info,
                    })

                return services

            errors.append(
                f"netstat gagal: {result.stderr.strip() or 'Tidak ada pesan error.'}"
            )

        except subprocess.TimeoutExpired:
            errors.append("Perintah netstat mengalami timeout.")
        except OSError as exc:
            errors.append(f"Gagal menjalankan netstat: {exc}")

    if not ss_path and not netstat_path:
        raise RuntimeError(
            "Executable ss dan netstat tidak ditemukan."
        )

    raise RuntimeError(
        "Gagal mendapatkan daftar listening services. "
        + " | ".join(errors)
    )


def get_process_names(process_info: str) -> set[str]:
    """Mengambil nama proses dari informasi socket."""

    if not process_info:
        return set()

    # Format ss: users:(("sshd",pid=1234,fd=3))
    ss_names = re.findall(r'\("([^"]+)"', process_info)

    if ss_names:
        return {name.lower() for name in ss_names}

    # Format netstat: 1234/sshd
    if "/" in process_info:
        process_name = process_info.split("/", 1)[1].strip()

        if process_name and process_name != "-":
            return {Path(process_name).name.lower()}

    return set()


def is_loopback_address(address: str) -> bool:
    """Memeriksa apakah alamat socket merupakan alamat loopback."""

    host = address.rsplit(":", 1)[0].strip()

    # Menghilangkan tanda kurung pada alamat IPv6.
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]

    # Menghilangkan scope ID IPv6, jika tersedia.
    host = host.split("%", 1)[0]

    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def is_approved_service(process_info: str) -> bool:
    """Memeriksa apakah proses termasuk daftar approved services."""

    process_names = get_process_names(process_info)

    if not process_names:
        return False

    approved_services = {
        Path(str(service)).name.lower()
        for service in APPROVED_SERVICES_SET
    }

    return bool(process_names & approved_services)


def main():
    task_vars = load_taskfile_vars(SCRIPT_DIR)

    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="audit.json",
        catalog=task_vars.get("ID", "K15"),
        nama=task_vars.get("NAMA", "Pengaturan Layanan Jaringan yang Mendengarkan Interface Network"),
        kode_cis=task_vars.get("KODE_CIS", "2.1.22"),
        judul_cis=task_vars.get("JUDUL_CIS", "Ensure only approved services are listening on a network interface"),
        versi_cis=task_vars.get("VERSI_CIS", "Ubuntu 24.04 LTS Benchmark v2.0.0"),
        regulasi=task_vars.get("REGULASI", "Pasal 35, Pasal 39"),
        kepatuhan=task_vars.get("KEPATUHAN", "UU PDP No. 27/2022"),
        log_type="audit",
    )

    lock_name = CATALOG_LOCKS.get("K15", "network_audit")
    lock_file = acquire_lock(lock_name, logger)

    start = perf_counter()
    
    try:
        # Ambil daftar layanan yang sedang listening
        listening_services = get_listening_services()

        if not listening_services:
            logger.log(
                LogStatus.COMPLIANT,
                "Result",
                "Hasil Audit: COMPLIANT - Tidak ditemukan TCP/UDP socket yang sedang listening.",
                duration_ms=(perf_counter() - start) * 1000,
            )
            sys.exit(1)

        unapproved_services = []

        for service in listening_services:
            process_info = service["process"]
            address = service["address"]

            # Loopback tidak dianggap sebagai layanan yang terbuka pada interface jaringan eksternal.
            if is_loopback_address(address):
                continue

            if not is_approved_service(process_info):
                process_names = get_process_names(process_info)
                process_name = (
                    ", ".join(sorted(process_names))
                    if process_names
                    else "Unknown Process"
                )

                unapproved_services.append(
                    f"{service['proto']} {address} ({process_name})"
                )

        if not unapproved_services:
            logger.log(
                LogStatus.COMPLIANT,
                "Result",
                "Hasil Audit: COMPLIANT - Semua layanan yang listening pada interface jaringan termasuk dalam daftar approved services.",
                duration_ms=(perf_counter() - start) * 1000,
            )
            sys.exit(0)

        logger.log(
            LogStatus.NON_COMPLIANT,
            "Result",
            "Hasil Audit: NON_COMPLIANT - Ditemukan layanan yang tidak disetujui sedang listening: " + ", ".join(unapproved_services),
            duration_ms=(perf_counter() - start) * 1000,
        )
        sys.exit(1)

    except Exception as e:
        logger.log_error(
            "K15", 
            "audit", 
            e,
            duration_ms=(perf_counter() - start) * 1000,
        )

    finally:
        release_lock(lock_file)


if __name__ == "__main__":
    main()