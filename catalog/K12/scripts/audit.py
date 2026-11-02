from __future__ import annotations
from pathlib import Path
from time import perf_counter
import os
import re
import shutil
import subprocess
import sys


SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parents[2]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import CATALOG_LOCKS

from pipeline.catalogutils import (
    LogStatus,
    BaseLogger,
    load_taskfile_vars,
    acquire_lock,
    release_lock,
)



def run_command(
    command: list[str],
    timeout: int = 60,
) -> subprocess.CompletedProcess:
    """Menjalankan perintah sistem dengan locale yang konsisten."""

    env = os.environ.copy()
    env["LC_ALL"] = "C"

    return subprocess.run(
        command,
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
        env=env,
    )


def require_command(command: str) -> str:
    """Memastikan executable tersedia."""

    executable = shutil.which(command)

    if not executable:
        raise RuntimeError(
            f"Perintah {command} tidak ditemukan."
        )

    return executable


# ============================================================
# APT Audit Checks
# ============================================================

def check_apt_availability() -> None:
    """Memastikan perintah APT yang dibutuhkan tersedia."""

    require_command("apt-get")
    require_command("apt-cache")
    require_command("apt-mark")


def check_pending_updates() -> tuple[bool, str, list[str]]:
    """
    Memeriksa paket yang masih dapat diperbarui.

    Menggunakan simulasi full-upgrade sehingga tidak mengubah
    atau memasang paket pada sistem.
    """

    apt_get = require_command("apt-get")

    try:
        result = run_command(
            [apt_get, "-s", "full-upgrade"],
            timeout=120,
        )

    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            "Pemeriksaan pembaruan APT mengalami timeout."
        ) from exc

    except OSError as exc:
        raise RuntimeError(
            f"Gagal menjalankan pemeriksaan APT: {exc}"
        ) from exc

    if result.returncode != 0:
        error = result.stderr.strip() or (
            "Tidak ada detail kesalahan dari APT."
        )
        raise RuntimeError(
            f"Gagal memeriksa pembaruan APT: {error}"
        )

    packages = re.findall(
        r"^Inst\s+([^\s]+)",
        result.stdout,
        re.MULTILINE,
    )

    summary = re.search(
        r"(\d+)\s+upgraded,\s+(\d+)\s+newly installed,\s+"
        r"(\d+)\s+to remove",
        result.stdout,
        re.IGNORECASE,
    )

    if not summary:
        raise RuntimeError(
            "Tidak dapat membaca ringkasan simulasi pembaruan APT."
        )

    upgraded = int(summary.group(1))
    newly_installed = int(summary.group(2))
    to_remove = int(summary.group(3))

    if upgraded > 0:
        if not packages:
            raise RuntimeError(
                "APT melaporkan paket yang perlu diperbarui, "
                "tetapi nama paket tidak berhasil diidentifikasi."
            )

        return (
            False,
            f"Ditemukan {upgraded} paket yang belum diperbarui: "
            + ", ".join(packages),
            packages,
        )

    if newly_installed > 0 or to_remove > 0:
        return (
            True,
            "Tidak ditemukan paket upgrade yang tertunda. "
            "Namun simulasi APT menunjukkan perubahan tambahan: "
            f"{newly_installed} paket baru dan "
            f"{to_remove} paket akan dihapus.",
            [],
        )

    return (
        True,
        "Tidak ditemukan paket yang perlu diperbarui.",
        [],
    )


def check_security_updates(
    packages: list[str],
) -> tuple[bool, str]:
    """
    Mengidentifikasi paket tertunda yang kandidat versinya
    berasal dari repositori keamanan.
    """

    if not packages:
        return (
            True,
            "Tidak ada paket tertunda yang perlu diperiksa.",
        )

    apt_cache = require_command("apt-cache")
    security_packages = []
    inspection_errors = []

    for package in packages:
        try:
            result = run_command(
                [apt_cache, "policy", package],
                timeout=15,
            )

        except (subprocess.TimeoutExpired, OSError):
            inspection_errors.append(package)
            continue

        if result.returncode != 0:
            inspection_errors.append(package)
            continue

        output = result.stdout

        candidate_match = re.search(
            r"^\s*Candidate:\s*(\S+)",
            output,
            re.MULTILINE,
        )

        if not candidate_match:
            inspection_errors.append(package)
            continue

        candidate = candidate_match.group(1)

        if candidate == "(none)":
            inspection_errors.append(package)
            continue

        version_pattern = re.compile(
            r"^\s*(?:\*\*\*\s+)?"
            + re.escape(candidate)
            + r"\s+\d+.*$",
            re.MULTILINE,
        )

        version_match = version_pattern.search(output)

        if not version_match:
            inspection_errors.append(package)
            continue

        start = version_match.end()

        next_version = re.search(
            r"^\s*(?:\*\*\*\s+)?\S+\s+\d+.*$",
            output[start:],
            re.MULTILINE,
        )

        end = (
            start + next_version.start()
            if next_version
            else len(output)
        )

        candidate_details = output[start:end].lower()

        is_security_update = re.search(
            r"-security(?:/|\s|$)|a=[^,\s]*-security\b",
            candidate_details,
        )

        if is_security_update:
            security_packages.append(package)

    if inspection_errors:
        raise RuntimeError(
            "Gagal mengidentifikasi asal kandidat paket: "
            + ", ".join(inspection_errors)
        )

    if security_packages:
        return (
            False,
            "Ditemukan pembaruan keamanan yang belum diterapkan: "
            + ", ".join(security_packages),
        )

    return (
        True,
        "Tidak ditemukan paket tertunda yang teridentifikasi "
        "berasal dari repositori keamanan.",
    )


# ============================================================
# Additional Audit Information
# ============================================================

def check_held_packages() -> list[str]:
    """Mengambil daftar paket yang ditahan oleh APT."""

    apt_mark = require_command("apt-mark")

    try:
        result = run_command(
            [apt_mark, "showhold"],
            timeout=15,
        )

    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(
            "Pemeriksaan held packages mengalami timeout."
        ) from exc

    except OSError as exc:
        raise RuntimeError(
            f"Gagal memeriksa held packages: {exc}"
        ) from exc

    if result.returncode != 0:
        error = result.stderr.strip() or (
            "Tidak ada detail kesalahan dari apt-mark."
        )
        raise RuntimeError(
            f"Gagal memeriksa held packages: {error}"
        )

    return [
        package.strip()
        for package in result.stdout.splitlines()
        if package.strip()
    ]


def check_reboot_required() -> str | None:
    """
    Memeriksa apakah sistem membutuhkan reboot.

    Mengembalikan pesan jika reboot diperlukan, atau None
    jika tidak ada kebutuhan reboot yang terdeteksi.
    """

    reboot_file = Path("/var/run/reboot-required")
    packages_file = Path("/var/run/reboot-required.pkgs")

    if not reboot_file.exists():
        return None

    if not reboot_file.is_file():
        raise RuntimeError(
            "File reboot-required ditemukan tetapi bukan file biasa."
        )

    try:
        packages = []

        if packages_file.is_file():
            packages = [
                line.strip()
                for line in packages_file.read_text(
                    encoding="utf-8"
                ).splitlines()
                if line.strip()
            ]

    except OSError as exc:
        raise RuntimeError(
            f"Gagal membaca informasi kebutuhan reboot: {exc}"
        ) from exc

    if packages:
        return (
            "Sistem membutuhkan reboot setelah pembaruan. "
            "Paket terkait: " + ", ".join(packages)
        )

    return "Sistem membutuhkan reboot setelah pembaruan."



def main() -> int:
    task_vars = load_taskfile_vars(SCRIPT_DIR)

    logger = BaseLogger(
        script_dir=SCRIPT_DIR,
        log_file_name="audit.json",
        catalog=task_vars.get("ID", "K12"),
        nama=task_vars.get("NAMA", "Memastikan Pembaruan, Patch, dan Perangkat Lunak Keamanan Terpasang"),
        kode_cis=task_vars.get("KODE_CIS", "1.2.2.1"),
        judul_cis=task_vars.get("JUDUL_CIS", "Ensure updates, patches, and additional security software are installed"),
        versi_cis=task_vars.get("VERSI_CIS", "Ubuntu 24.04 LTS Benchmark v2.0.0"),
        regulasi=task_vars.get("REGULASI", "Pasal 35, Pasal 39"),
        kepatuhan=task_vars.get("KEPATUHAN", "UU PDP No. 27/2022"),
        log_type="audit",
    )

    lock_name = CATALOG_LOCKS.get("K12", "system_updates")
    lock_file = acquire_lock(lock_name, logger)

    start = perf_counter()

    try:
        findings: list[str] = []
        advisories: list[str] = []

        # Pastikan APT tersedia.
        check_apt_availability()

        # Periksa paket yang masih tertunda.
        updates_ok, updates_message, packages = (
            check_pending_updates()
        )

        findings.append(
            f"- Pending Updates [{'Success' if updates_ok else 'Warning'}] "
            f": {updates_message}"
        )

        # Periksa apakah paket tertunda merupakan pembaruan keamanan.
        security_ok, security_message = check_security_updates(
            packages
        )

        findings.append(
            f"- Security Updates "
            f"[{'Success' if security_ok else 'Warning'}] "
            f": {security_message}"
        )

        # Paket held hanya menjadi informasi tambahan.
        held_packages = check_held_packages()

        if held_packages:
            advisories.append(
                "Paket yang ditahan APT: "
                + ", ".join(held_packages)
            )
        else:
            advisories.append(
                "Tidak ditemukan paket yang ditahan APT."
            )

        # Kebutuhan reboot juga menjadi informasi tambahan.
        reboot_message = check_reboot_required()

        if reboot_message:
            advisories.append(reboot_message)
        else:
            advisories.append(
                "Sistem tidak menunjukkan kebutuhan reboot."
            )

        # Tentukan hasil berdasarkan pemeriksaan utama.
        failed_checks = []

        if not updates_ok:
            failed_checks.append("Pending Updates")

        if not security_ok:
            failed_checks.append("Security Updates")

        details = findings + [
            f"- Advisory : {message}"
            for message in advisories
        ]

        if failed_checks:
            logger.log(
                LogStatus.NON_COMPLIANT,
                "Result",
                "Hasil Audit: NON_COMPLIANT - "
                "Ditemukan pembaruan paket yang belum diterapkan.\n"
                + "\n".join(details),
                duration_ms=(perf_counter() - start) * 1000,
            )
            sys.exit(1)

        logger.log(
            LogStatus.COMPLIANT,
            "Result",
            "Hasil Audit: COMPLIANT - "
            "Tidak ditemukan paket upgrade yang tertunda.\n"
            + "\n".join(details),
            duration_ms=(perf_counter() - start) * 1000,
        )
        sys.exit(0)

    except Exception as e:
        logger.log_error(
            "K12", 
            "audit", 
            e,
            duration_ms=(perf_counter() - start) * 1000,
        )
        sys.exit(2)
    finally:
        release_lock(lock_file)


if __name__ == "__main__":
    main()
