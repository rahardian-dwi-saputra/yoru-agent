import yaml
import json
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional
from config.api import CATALOGS_DIR
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
        judul_cis = str(vars_data.get("JUDUL_CIS") or "")
        versi_cis = str(vars_data.get("VERSI_CIS") or "")
        regulasi = str(vars_data.get("REGULASI") or "")
        kepatuhan = str(vars_data.get("KEPATUHAN") or "")
        framework = str(vars_data.get("FRAMEWORK") or "")
        
        # Penanganan multiline string deskripsi yang aman dari None
        deskripsi_raw = vars_data.get("DESKRIPSI") or ""
        deskripsi = str(deskripsi_raw).strip().replace("\n", " ")
        
        risiko = str(vars_data.get("RISIKO") or "")
        kategori = str(vars_data.get("KATEGORI") or "")
        
        # Konversi fleksibel untuk boolean AUDIT_ONLY
        audit_only_val = vars_data.get("AUDIT_ONLY", False)
        if isinstance(audit_only_val, str):
            audit_only = audit_only_val.lower() == "true"
        else:
            audit_only = bool(audit_only_val)

        # Penanganan multiline string deskripsi yang aman dari None
        pesan_hardening_raw = vars_data.get("PESAN_HARDENING") or ""
        pesan_hardening = str(pesan_hardening_raw).strip().replace("\n", " ")

        if "⚠️ PERINGATAN:" in pesan_hardening:
            pesan_hardening = pesan_hardening.replace(" ⚠️ PERINGATAN: ", "\n⚠️ PERINGATAN:\n")

        if "⚠️ DAMPAK OPERASIONAL:" in pesan_hardening:
            pesan_hardening = pesan_hardening.replace(" ⚠️ DAMPAK OPERASIONAL: ", "\n⚠️ DAMPAK OPERASIONAL:\n")

        pesan_rollback_raw = vars_data.get("PESAN_ROLLBACK") or ""
        pesan_rollback = str(pesan_rollback_raw).strip().replace("\n", " ")

        if "⚠️ RISIKO KEAMANAN:" in pesan_rollback:
            pesan_rollback = pesan_rollback.replace(" ⚠️ RISIKO KEAMANAN: ", "\n⚠️ RISIKO KEAMANAN:\n")

        if "⚠️ RISIKO:" in pesan_rollback:
            pesan_rollback = pesan_rollback.replace(" ⚠️ RISIKO: ", "\n⚠️ RISIKO:\n")


        return CatalogMetadata(
            id=catalog_id,
            nama=nama,
            kode_cis=kode_cis,
            judul_cis=judul_cis,
            versi_cis=versi_cis,
            regulasi=regulasi,
            kepatuhan=kepatuhan,
            framework=framework,
            deskripsi=deskripsi,
            risiko=risiko,
            kategori=kategori,
            audit_only=audit_only,
            pesan_hardening=pesan_hardening,
            pesan_rollback=pesan_rollback,
        )
    except Exception:
        return None


def get_available_catalogs() -> List[CatalogMetadata]:
    """Mengambil daftar folder katalog beserta metadatanya dari file Taskfile.yml."""
    if not CATALOGS_DIR.exists():
        return []

    results: List[CatalogMetadata] = []

    catalog_dirs = sorted(
        [
            d
            for d in CATALOGS_DIR.iterdir()
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
                    judul_cis="-",
                    versi_cis="-",
                    regulasi="-",
                    kepatuhan="-",
                    framework="-",
                    deskripsi="-",
                    risiko="-",
                    kategori="-",
                    audit_only=False,
                    pesan_hardening="-",
                    pesan_rollback="-",
                )
            )

    return results



def read_latest_log(target_path: Path, action: str) -> Optional[Dict[str, Any]]:
    """Membaca log JSON terakhir dari file log katalog."""
    log_filename = f"{action.lower()}.json"
    log_path = target_path / "logs" / log_filename

    if log_path.is_file():
        try:
            with open(log_path, "r", encoding="utf-8") as f:
                content = f.read().strip()
                
            if not content:
                return None

            # 1. Coba parse sebagai JSON tunggal
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                # 2. Jika gagal (karena mode append/JSON lines), ambil baris non-kosong terakhir
                lines = [line.strip() for line in content.splitlines() if line.strip()]
                if lines:
                    return json.loads(lines[-1])

        except Exception as e:
            return {"error_reading_log": f"Gagal membaca/parse {log_filename}: {str(e)}"}

    return None


def run_taskfile(catalog_id: str, action: str) -> CatalogResult:
    """Mengeksekusi Taskfile.yml pada katalog tertentu dan membaca log hasilnya."""
    target_path = CATALOGS_DIR / catalog_id
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