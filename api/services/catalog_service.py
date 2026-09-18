import yaml
import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

from api.config import CATALOG_DIR
from api.schemas.catalog import CatalogMetadata, CatalogResult


def parse_taskfile_metadata(taskfile_path: Path) -> Optional[CatalogMetadata]:
    """Membaca file Taskfile.yml dan meng-extract metadata CIS dari blok vars:"""
    if not taskfile_path.is_file():
        return None

    try:
        with open(taskfile_path, "r", encoding="utf-8", errors="ignore") as f:
            content = yaml.safe_load(f)

        vars_data = content.get("vars", {}) if isinstance(content, dict) else {}

        catalog_id = str(vars_data.get("ID") or taskfile_path.parent.name)
        nama = str(vars_data.get("NAMA") or "")
        kode_cis = str(vars_data.get("KODE_CIS") or "")
        cis_judul = str(vars_data.get("CIS_JUDUL") or "")
        
        # Penanganan multiline string deskripsi yang aman dari None
        deskripsi_raw = vars_data.get("DESKRIPSI") or ""
        deskripsi = str(deskripsi_raw).strip()
        
        resiko = str(vars_data.get("RISIKO") or "")
        kategori = str(vars_data.get("KATEGORI") or "")
        
        # Konversi fleksibel untuk boolean AUDIT_ONLY
        audit_only_val = vars_data.get("AUDIT_ONLY", False)
        if isinstance(audit_only_val, str):
            audit_only = audit_only_val.lower() == "true"
        else:
            audit_only = bool(audit_only_val)

        return CatalogMetadata(
            id=catalog_id,
            nama=nama,
            kode_cis=kode_cis,
            cis_judul=cis_judul,
            deskripsi=deskripsi,
            resiko=resiko,
            kategori=kategori,
            audit_only=audit_only,
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



def read_latest_log(target_path: Path, action: str) -> Optional[Dict[str, Any]]:
    """Membaca file log JSON sesuai aksi (audit.json, hardening.json, rollback.json)."""
    log_filename = f"{action.lower()}.json"
    log_path = target_path / log_filename

    if log_path.is_file():
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            return {"error_reading_log": f"Gagal membaca/parse {log_filename}: {str(e)}"}
    
    return None


def run_taskfile(catalog_id: str, action: str) -> CatalogResult:
    """Mengeksekusi Taskfile.yml pada katalog tertentu dan membaca log hasilnya."""
    target_path = CATALOG_DIR / catalog_id
    taskfile_path = target_path / "Taskfile.yml"

    # Validasi keberadaan direktori & Taskfile
    if not target_path.exists() or not taskfile_path.exists():
        return CatalogResult(
            catalog=catalog_id,
            status="FAILED",
            output="",
            error=f"Katalog '{catalog_id}' atau Taskfile.yml tidak ditemukan.",
            log_data=None,
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

        # Membaca log file terkait setelah eksekusi selesai
        log_content = read_latest_log(target_path, action)

        if process.returncode == 0:
            return CatalogResult(
                catalog=catalog_id,
                status="SUCCESS",
                output=process.stdout.strip(),
                log_data=log_content,
            )
        else:
            return CatalogResult(
                catalog=catalog_id,
                status="FAILED",
                output=process.stdout.strip(),
                error=process.stderr.strip(),
                log_data=log_content,
            )

    except FileNotFoundError:
        return CatalogResult(
            catalog=catalog_id,
            status="FAILED",
            output="",
            error="Binary 'task' (Taskfile runner) tidak terinstall di sistem.",
            log_data=None,
        )
    except Exception as e:
        return CatalogResult(
            catalog=catalog_id,
            status="FAILED",
            output="",
            error=f"Terjadi error saat eksekusi: {str(e)}",
            log_data=None,
        )