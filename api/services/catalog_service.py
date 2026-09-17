import re
import subprocess
from pathlib import Path
from typing import List, Optional

from api.config import CATALOG_DIR
from api.schemas.catalog import CatalogMetadata, CatalogResult


def parse_taskfile_metadata(taskfile_path: Path) -> Optional[CatalogMetadata]:
    """Membaca file Taskfile.yml dan meng-extract metadata CIS dari blok vars:"""
    if not taskfile_path.is_file():
        return None

    meta = {
        "id": taskfile_path.parent.name,
        "nama": "",
        "kode_cis": "",
        "cis_judul": "",
        "resiko": "",
        "kategori": "",
        "audit_only": False,
    }

    try:
        with open(taskfile_path, "r", encoding="utf-8", errors="ignore") as f:
            for line in f:
                line_stripped = line.strip()

                if line_stripped.startswith("#"):
                    continue

                for key in ["ID", "NAMA", "KODE_CIS", "CIS_JUDUL", "RISIKO", "KATEGORI"]:
                    pattern = rf"^{key}:\s*[\"']?(.*?)[\"']?$"
                    match = re.match(pattern, line_stripped, re.IGNORECASE)
                    if match:
                        meta[key.lower()] = match.group(1).strip()

                match_audit_only = re.match(
                    r"^AUDIT_ONLY:\s*(true|false)", line_stripped, re.IGNORECASE
                )
                if match_audit_only:
                    meta["audit_only"] = match_audit_only.group(1).lower() == "true"

        return CatalogMetadata(
            id=meta["id"],
            nama=meta["nama"],
            kode_cis=meta["kode_cis"],
            cis_judul=meta["cis_judul"],
            resiko=meta["risiko"],
            kategori=meta["kategori"],
            audit_only=meta["audit_only"],
        )
    except Exception:
        return None


def get_available_catalogs() -> List[CatalogMetadata]:
    """Mengambil daftar folder katalog beserta metadatanya dari file Taskfile.yml."""
    if not CATALOG_DIR.exists():
        return []

    results: List[CatalogMetadata] = []

    catalog_dirs = sorted(
        [
            d
            for d in CATALOG_DIR.iterdir()
            if d.is_dir() and d.name.upper().startswith("K")
        ],
        key=lambda x: x.name,
    )

    for cat_dir in catalog_dirs:
        taskfile_path = cat_dir / "Taskfile.yml"
        metadata = parse_taskfile_metadata(taskfile_path)

        if metadata:
            results.append(metadata)
        else:
            results.append(
                CatalogMetadata(
                    id=cat_dir.name,
                    nama="Katalog " + cat_dir.name,
                    kode_cis="-",
                    cis_judul="-",
                    resiko="-",
                    kategori="-",
                )
            )

    return results


def run_taskfile(catalog_id: str, action: str) -> CatalogResult:
    """Mengeksekusi Taskfile.yml pada katalog tertentu."""
    target_path = CATALOG_DIR / catalog_id
    taskfile_path = target_path / "Taskfile.yml"

    if not target_path.exists() or not taskfile_path.exists():
        return CatalogResult(
            catalog=catalog_id,
            status="FAILED",
            output="",
            error=f"Katalog '{catalog_id}' atau Taskfile.yml tidak ditemukan.",
        )

    cmd = ["task", action]

    try:
        process = subprocess.run(
            cmd,
            cwd=target_path,
            capture_output=True,
            text=True,
            check=False,
        )

        if process.returncode == 0:
            return CatalogResult(
                catalog=catalog_id,
                status="SUCCESS",
                output=process.stdout.strip(),
            )
        else:
            return CatalogResult(
                catalog=catalog_id,
                status="FAILED",
                output=process.stdout.strip(),
                error=process.stderr.strip(),
            )

    except FileNotFoundError:
        return CatalogResult(
            catalog=catalog_id,
            status="FAILED",
            output="",
            error="Binary 'task' (Taskfile runner) tidak terinstall di sistem.",
        )
    except Exception as e:
        return CatalogResult(
            catalog=catalog_id,
            status="FAILED",
            output="",
            error=f"Terjadi error saat eksekusi: {str(e)}",
        )