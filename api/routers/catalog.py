from typing import Dict
from fastapi import APIRouter, HTTPException, status

from api.schemas.catalog import (
    CatalogListResponse,
    CatalogMetadata,
    CatalogResult,
    ExecutionRequest,
    ExecutionResponse,
)
from api.services.catalog_service import get_available_catalogs, run_taskfile

router = APIRouter(prefix="/api/v1", tags=["Catalog & Agent"])


@router.get(
    "/catalogs",
    response_model=CatalogListResponse,
    summary="Mendapatkan Daftar Katalog Tersedia",
)
async def list_catalogs():
    """Mengembalikan semua katalog yang tersedia di direktori catalog/ secara otomatis."""
    catalogs = get_available_catalogs()
    return {
        "total": len(catalogs),
        "catalogs": catalogs,
    }


@router.post(
    "/agent/execute",
    response_model=ExecutionResponse,
    summary="Endpoint Universal Eksekusi Agent",
)
async def execute_agent_task(payload: ExecutionRequest):
    """Endpoint universal untuk menjalankan aksi (audit, hardening, rollback) pada satu atau banyak katalog."""
    action = payload.action
    requested_catalogs = payload.catalogs

    # 1. Validasi Konfirmasi
    if action in ["hardening", "rollback"] and not payload.confirmed:
        return ExecutionResponse(
            status="NEED_CONFIRMATION",
            action=action,
            requires_confirmation=True,
            message=(
                f"Aksi '{action}' akan mengubah konfigurasi server. "
                f"Apakah Anda yakin ingin melanjutkan eksekusi pada katalog {requested_catalogs}? "
                "Kirimkan konfirmasi dengan nilai 'confirmed: True' untuk mengeksekusi."
            ),
            results=[],
        )

    # 2. Lookup Katalog
    all_catalogs_list = get_available_catalogs()
    available_catalogs_map: Dict[str, CatalogMetadata] = {
        cat.id.upper(): cat for cat in all_catalogs_list
    }

    if "ALL" in [c.upper() for c in requested_catalogs]:
        target_catalog_ids = list(available_catalogs_map.keys())
    else:
        target_catalog_ids = [
            c.upper() for c in requested_catalogs if c.upper() in available_catalogs_map
        ]

    if not target_catalog_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tidak ada katalog valid yang ditentukan atau direktori catalog/ kosong.",
        )

    # 3. Validasi AUDIT_ONLY
    if action in ["hardening", "rollback"]:
        blocked_catalogs = [
            cat_id
            for cat_id in target_catalog_ids
            if available_catalogs_map[cat_id].audit_only
        ]

        if blocked_catalogs:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Aksi '{action}' ditolak! Katalog berikut dikonfigurasi sebagai 'AUDIT_ONLY' "
                    f"dan tidak mengizinkan aksi perbaikan/pemulihan: {blocked_catalogs}"
                ),
            )

    # 4. Eksekusi Task
    execution_results: list[CatalogResult] = []
    for cat_id in target_catalog_ids:
        result = run_taskfile(cat_id, action)
        execution_results.append(result)

    return ExecutionResponse(
        status="COMPLETED",
        action=action,
        requires_confirmation=False,
        message=f"Aksi '{action}' selesai diproses untuk {len(execution_results)} katalog.",
        results=execution_results,
    )