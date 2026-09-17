from __future__ import annotations
from pathlib import Path
from typing import List, Dict, Any
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
    release_lock
)

# Daftar layanan / port / proses yang disetujui (dapat disesuaikan dengan kebutuhan lingkungan)
APPROVED_SERVICES = {
    "sshd",
    "systemd-resolve",
    "chronyd",
    "ntpd"
}


def get_listening_services() -> List[Dict[str, Any]]:
    """Mendapatkan daftar socket/layanan yang sedang listening pada network interface."""
    services = []
    
    # Mencoba menggunakan perintah 'ss' terlebih dahulu
    try:
        res = subprocess.run(
            ["ss", "-tulnpt"],
            capture_output=True,
            text=True,
        )
        if res.returncode == 0:
            lines = res.stdout.strip().splitlines()
            if len(lines) > 1:
                # Lewati header line
                for line in lines[1:]:
                    parts = line.split()
                    if len(parts) >= 5:
                        proto = parts[0]
                        local_addr = parts[4]
                        process_info = parts[6] if len(parts) >= 7 else ""
                        
                        services.append({
                            "proto": proto,
                            "address": local_addr,
                            "process": process_info
                        })
            return services
    except Exception:
        pass

    # Fallback ke netstat jika ss tidak tersedia/gagal
    try:
        res = subprocess.run(
            ["netstat", "-tulnp"],
            capture_output=True,
            text=True,
        )
        if res.returncode == 0:
            lines = res.stdout.strip().splitlines()
            for line in lines:
                if "LISTEN" in line or "udp" in line:
                    parts = line.split()
                    if len(parts) >= 4:
                        proto = parts[0]
                        local_addr = parts[3]
                        process_info = parts[-1] if "/" in parts[-1] else ""
                        
                        services.append({
                            "proto": proto,
                            "address": local_addr,
                            "process": process_info
                        })
    except Exception:
        pass

    return services


def main():
    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="audit.json",
        catalog="K10",
        cis_id="2.1.22",
        log_type="audit",
    )

    lock_file = acquire_lock_ufw(logger)

    try:
        listening_services = get_listening_services()

        if not listening_services:
            logger.log(
                "COMPLIANT",
                "Result",
                "Hasil Audit: COMPLIANT - Tidak ada layanan tak dikenal yang terdeteksi listening pada interface jaringan.",
            )
            return

        unapproved_found = []

        for svc in listening_services:
            process_name = svc["process"].lower()
            # Cek apakah nama proses mengandung salah satu dari daftar approved services
            is_approved = any(approved in process_name for approved in APPROVED_SERVICES)
            
            # Khusus loopback (127.0.0.1 atau ::1), biasanya diperbolehkan kecuali kebijakan mewajibkan sebaliknya
            is_loopback = svc["address"].startswith("127.") or svc["address"].startswith("[::1]") or svc["address"].startswith("::1")

            if not is_approved and not is_loopback:
                unapproved_found.append(f"{svc['proto']} {svc['address']} ({svc['process'] or 'Unknown Process'})")

        if not unapproved_found:
            logger.log(
                "COMPLIANT",
                "Result",
                "Hasil Audit: COMPLIANT - Semua layanan yang listening pada network interface sudah sesuai dengan daftar approved services.",
            )
        else:
            unapproved_str = ", ".join(unapproved_found)
            logger.log(
                "NON_COMPLIANT",
                "Result",
                f"Hasil Audit: NON_COMPLIANT - Ditemukan layanan yang tidak disetujui listening pada network interface: {unapproved_str}.",
            )

    except Exception as e:
        logger.log_error("K11", "audit", e)

    finally:
        release_lock(lock_file)


if __name__ == "__main__":
    main()