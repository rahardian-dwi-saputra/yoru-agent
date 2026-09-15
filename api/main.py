from __future__ import annotations
from pathlib import Path
from typing import List, Literal, Optional
from fastapi import FastAPI, HTTPException, Status
from pydantic import BaseModel, Field
import uvicorn
import subprocess


# Inisialisasi FastAPI
app = FastAPI(
    title="Yoru Agent API",
    description="API Universal untuk Audit, Hardening, dan Rollback Konfigurasi Server Keamanan",
    version="1.0.0",
)

# Root direktori proyek (yoru-agent/)
API_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = API_DIR.parent
CATALOG_DIR = PROJECT_ROOT / "catalog"


# --- PYDANTIC SCHEMAS ---

class ExecutionRequest(BaseModel):
    action: Literal["audit", "hardening", "rollback"] = Field(
        ..., description="Aksi yang akan dijalankan."
    )
    catalogs: List[str] = Field(
        ...,
        description="Daftar ID Katalog (misal ['K01', 'K03']) atau ['ALL'] untuk semua katalog.",
        examples=[["K03", "K04"]],
    )
    confirmed: bool = Field(
        default=False,
        description="Konfirmasi persetujuan user. Wajib True untuk aksi 'hardening' dan 'rollback'.",
    )


class CatalogResult(BaseModel):
    catalog: str
    status: Literal["SUCCESS", "FAILED", "SKIPPED", "CANCELLED"]
    output: str
    error: Optional[str] = None


class ExecutionResponse(BaseModel):
    status: str
    action: str
    requires_confirmation: bool = False
    message: str
    results: List[CatalogResult] = []


# --- HELPER FUNCTIONS ---

def get_available_catalogs() -> List[str]:
    """Mengambil daftar folder katalog secara dinamis dari /catalog yang berawalan huruf 'K'."""
    if not CATALOG_DIR.exists():
        return []
    return sorted(
        [
            d.name
            for d in CATALOG_DIR.iterdir()
            if d.is_dir() and d.name.startswith("K")
        ]
    )


def run_taskfile(catalog_id: str, action: str) -> CatalogResult:
    """Mengeksekusi Taskfile.yml pada katalog tertentu."""
    target_path = CATALOG_DIR / catalog_id
    taskfile_path = target_path / "Taskfile.yml"

    # Validasi keberadaan katalog & Taskfile
    if not target_path.exists() or not taskfile_path.exists():
        return CatalogResult(
            catalog=catalog_id,
            status="FAILED",
            output="",
            error=f"Katalog '{catalog_id}' atau Taskfile.yml tidak ditemukan.",
        )

    # Perintah eksekusi task (misal: task audit)
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


# --- API ENDPOINTS ---

@app.get("/api/v1/catalogs", summary="Mendapatkan Daftar Katalog Tersedia")
async def list_catalogs():
    """Mengembalikan semua katalog yang tersedia di direktori catalog/ secara otomatis."""
    catalogs = get_available_catalogs()
    return {
        "total": len(catalogs),
        "catalogs": catalogs,
    }


@app.post(
    "/api/v1/agent/execute",
    response_model=ExecutionResponse,
    summary="Endpoint Universal Eksekusi Agent",
)
async def execute_agent_task(payload: ExecutionRequest):
    """
    Endpoint universal untuk menjalankan aksi (audit, hardening, rollback) pada satu atau banyak katalog.
    - Untuk aksi 'hardening' atau 'rollback', properti `confirmed` HARUS bernilai `True` ('IYA').
    - Penggunaan 'ALL' pada `catalogs` akan otomatis mengeksekusi seluruh katalog yang ada.
    """
    action = payload.action
    requested_catalogs = payload.catalogs

    # 1. MEKANISME KONFIRMASI (USER APPROVAL CHECK)
    if action in ["hardening", "rollback"] and not payload.confirmed:
        return ExecutionResponse(
            status="NEED_CONFIRMATION",
            action=action,
            requires_confirmation=True,
            message=(
                f"Aksi '{action}' akan mengubah konfigurasi server. "
                f"Apakah Anda yakin ingin melanjutkan eksekusi pada katalog {requested_catalogs}? "
                "Kirimkan konfirmasi dengan nilai 'confirmed: True' (IYA) untuk mengeksekusi."
            ),
            results=[],
        )

    # 2. RESOLUSI KATALOG DINAMIS
    available_catalogs = get_available_catalogs()

    if "ALL" in [c.upper() for c in requested_catalogs]:
        target_catalogs = available_catalogs
    else:
        # Bersihkan kapitalisasi
        target_catalogs = [c.upper() for c in requested_catalogs]

    if not target_catalogs:
        raise HTTPException(
            status_code=Status.HTTP_400_BAD_REQUEST,
            detail="Tidak ada katalog valid yang ditentukan atau direktori catalog/ kosong.",
        )

    # 3. EKSEKUSI TASK UNTUK SETIAP KATALOG
    execution_results: List[CatalogResult] = []

    for cat_id in target_catalogs:
        result = run_taskfile(cat_id, action)
        execution_results.append(result)

    return ExecutionResponse(
        status="COMPLETED",
        action=action,
        requires_confirmation=False,
        message=f"Aksi '{action}' selesai diproses untuk {len(execution_results)} katalog.",
        results=execution_results,
    )


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)