from typing import Dict, List
from fastapi import APIRouter, Depends, HTTPException, Request, status

from api.config import limiter
from api.dependencies import verify_api_key
from api.schemas.catalog import (
    AuditRequest,
    CatalogListResponse,
    CatalogMetadata,
    CatalogResult,
    ExecutionResponse,
    HardeningConfirmRequest,
    HardeningInitRequest,
    HardeningInitResponse,
    HardeningPlanItem,
    RollbackConfirmRequest,
    RollbackInitRequest,
    ActionPlanInitResponse,
    ActionPlanItem,
)
from api.services.catalog_service import get_available_catalogs, run_taskfile
from api.services.plan_service import (
    create_hardening_plan,
    get_plan,
    is_plan_valid,
    update_and_expire_plan,
    create_action_plan,
)

router = APIRouter(
    prefix="/api/v1", 
    tags=["Catalog & Agent"],
    dependencies=[Depends(verify_api_key)]
)


@router.get(
    "/catalogs",
    response_model=CatalogListResponse,
    summary="Mendapatkan Daftar Katalog Tersedia",
)
@limiter.limit("20/minute")
async def list_catalogs(request: Request):
    """Mengembalikan semua katalog yang tersedia di direktori catalog/ secara otomatis."""
    catalogs = get_available_catalogs()
    return {
        "total": len(catalogs),
        "catalogs": catalogs,
    }


@router.post(
    "/agent/audit",
    response_model=ExecutionResponse,
    summary="Endpoint Universal Khusus Audit Catalog",
)
@limiter.limit("10/minute")
async def audit_agent_task(request: Request, payload: AuditRequest):
    """Endpoint universal khusus untuk menjalankan audit pada satu/banyak katalog atau ALL.
    
    Fitur:
    - Tanpa perlu konfirmasi persetujuan user.
    - Mendukung masukan berupa list ID spesifik (contoh: `["K01", "K02"]`) atau `["ALL"]`.
    - Otomatis mengeksekusi `task audit` dan membaca file `logs/audit.json`.
    """
    requested_catalogs = payload.catalogs

    # 1. RESOLUSI KATALOG DINAMIS
    all_catalogs_list = get_available_catalogs()
    available_catalogs_map: Dict[str, CatalogMetadata] = {
        cat.id.upper(): cat for cat in all_catalogs_list
    }

    # Jika memilih 'ALL', ambil seluruh katalog yang tersedia
    if "ALL" in [c.upper() for c in requested_catalogs]:
        target_catalog_ids = list(available_catalogs_map.keys())
    else:
        # Filter katalog sesuai input yang valid di server
        target_catalog_ids = [
            c.upper() for c in requested_catalogs if c.upper() in available_catalogs_map
        ]

    if not target_catalog_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tidak ada katalog valid yang ditentukan atau direktori catalog/ kosong.",
        )

    # 2. EKSEKUSI TASK AUDIT & BACA LOG JSON
    execution_results: list[CatalogResult] = []

    for cat_id in target_catalog_ids:
        # Menjalankan task dengan action "audit"
        result = run_taskfile(cat_id, "audit")
        execution_results.append(result)

    return ExecutionResponse(
        status="COMPLETED",
        action="audit",
        requires_confirmation=False,
        message=f"Aksi 'audit' selesai diproses untuk {len(execution_results)} katalog.",
        results=execution_results,
    )


# 1. Init Hardening Plan
@router.post(
    "/agent/hardening/init",
    response_model=HardeningInitResponse,
    summary="Inisialisasi Action Plan Hardening",
)
@limiter.limit("20/minute")
async def init_hardening_plan(request: Request, payload: HardeningInitRequest):
    requested_catalogs = payload.catalogs

    # 1. Resolusi Katalog
    all_catalogs_list = get_available_catalogs()
    available_catalogs_map: Dict[str, CatalogMetadata] = {
        cat.id.upper(): cat for cat in all_catalogs_list
    }

    is_all = "ALL" in [c.upper() for c in requested_catalogs]

    if is_all:
        target_catalog_ids = list(available_catalogs_map.keys())
    else:
        target_catalog_ids = [
            c.upper()
            for c in requested_catalogs
            if c.upper() in available_catalogs_map
        ]

    if not target_catalog_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tidak ada katalog valid yang ditentukan.",
        )

    # 2. Proteksi AUDIT_ONLY
    blocked_catalogs = [
        cat_id
        for cat_id in target_catalog_ids
        if available_catalogs_map[cat_id].audit_only
    ]
    if blocked_catalogs:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Katalog berikut berstatus AUDIT_ONLY dan tidak bisa di-hardening: {blocked_catalogs}",
        )

    plans_result: List[HardeningPlanItem] = []

    # 3. Alur untuk Mode 'ALL'
    if is_all:
        plan_data = create_hardening_plan(catalogs=target_catalog_ids)
        plans_result.append(HardeningPlanItem(**plan_data))
        msg = "Action plan untuk seluruh katalog berhasil dibuat. Silakan lakukan konfirmasi."

    # 4. Alur untuk Single / Specific Catalogs
    else:
        for cat_id in target_catalog_ids:
            plan_data = create_hardening_plan(
                catalogs=[cat_id], catalog_single=cat_id
            )
            plans_result.append(HardeningPlanItem(**plan_data))
        msg = f"Action plan untuk {len(plans_result)} katalog berhasil dibuat. Konfirmasi diperlukan per katalog."

    return HardeningInitResponse(
        status="PENDING_APPROVAL",
        message=msg,
        is_all_mode=is_all,
        plans=plans_result,
    )


# 2. Confirm & Execute Hardening
@router.post(
    "/agent/hardening/confirm",
    response_model=ExecutionResponse,
    summary="Eksekusi Hardening Setelah Konfirmasi User",
)
@limiter.limit("20/minute")
async def confirm_hardening_plan(
    request: Request, payload: HardeningConfirmRequest
):
    plan_data = get_plan(payload.plan_id)

    # Validasi Keberadaan Plan
    if not plan_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Action plan tidak ditemukan.",
        )

    # Pengecekan Jika Approved = False (Ditolak User)
    if not payload.approved:
        update_and_expire_plan(payload.plan_id, status="rejected_by_user")
        return ExecutionResponse(
            status="REJECTED",
            action="hardening",
            requires_confirmation=False,
            message="Permintaan hardening ditolak oleh user.",
            results=[],
        )

    # Pengecekan Masa Berlaku (Expired Check)
    if not is_plan_valid(plan_data):
        update_and_expire_plan(payload.plan_id, status="expired")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Action plan sudah kadaluwarsa (expired) atau sudah pernah digunakan.",
        )

    # Validasi Katalog untuk Mode Non-ALL
    target_catalogs = plan_data.get("catalogs", [])
    single_catalog_in_plan = plan_data.get("catalog")

    if single_catalog_in_plan:
        if (
            not payload.catalog
            or payload.catalog.upper() != single_catalog_in_plan.upper()
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Parameter catalog tidak sesuai dengan Action Plan ({single_catalog_in_plan}).",
            )

    # Eksekusi Hardening & Update Plan Menjadi Expired
    execution_results: List[CatalogResult] = []

    for cat_id in target_catalogs:
        # Panggil task execution dengan action "hardening"
        res = run_taskfile(cat_id, "hardening")
        execution_results.append(res)

    # Tandai plan sebagai terpakai / expired
    update_and_expire_plan(payload.plan_id, status="executed")

    return ExecutionResponse(
        status="COMPLETED",
        action="hardening",
        requires_confirmation=False,
        message=f"Aksi 'hardening' selesai diproses untuk {len(execution_results)} katalog.",
        results=execution_results,
    )


@router.post(
    "/agent/rollback/init",
    response_model=ActionPlanInitResponse,
    summary="Inisialisasi Action Plan Rollback",
)
@limiter.limit("20/minute")
async def init_rollback_plan(request: Request, payload: RollbackInitRequest):
    requested_catalogs = payload.catalogs

    # 1. Resolusi Katalog
    all_catalogs_list = get_available_catalogs()
    available_catalogs_map: Dict[str, CatalogMetadata] = {
        cat.id.upper(): cat for cat in all_catalogs_list
    }

    is_all = "ALL" in [c.upper() for c in requested_catalogs]

    if is_all:
        target_catalog_ids = list(available_catalogs_map.keys())
    else:
        target_catalog_ids = [
            c.upper()
            for c in requested_catalogs
            if c.upper() in available_catalogs_map
        ]

    if not target_catalog_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tidak ada katalog valid yang ditentukan.",
        )

    # 2. Proteksi AUDIT_ONLY
    blocked_catalogs = [
        cat_id
        for cat_id in target_catalog_ids
        if available_catalogs_map[cat_id].audit_only
    ]
    if blocked_catalogs:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Katalog berikut berstatus AUDIT_ONLY dan tidak bisa di-rollback: {blocked_catalogs}",
        )

    plans_result: List[ActionPlanItem] = []

    # 3. Alur untuk Mode 'ALL'
    if is_all:
        plan_data = create_action_plan(action="rollback", catalogs=target_catalog_ids)
        plans_result.append(ActionPlanItem(**plan_data))
        msg = "Action plan rollback untuk seluruh katalog berhasil dibuat. Silakan lakukan konfirmasi."

    # 4. Alur untuk Single / Specific Catalogs
    else:
        for cat_id in target_catalog_ids:
            plan_data = create_action_plan(
                action="rollback", catalogs=[cat_id], catalog_single=cat_id
            )
            plans_result.append(ActionPlanItem(**plan_data))
        msg = f"Action plan rollback untuk {len(plans_result)} katalog berhasil dibuat. Konfirmasi diperlukan per katalog."

    return ActionPlanInitResponse(
        status="PENDING_APPROVAL",
        message=msg,
        is_all_mode=is_all,
        plans=plans_result,
    )


# -------------------------------------------------------------------
# 2. CONFIRM & EXECUTE ROLLBACK
# -------------------------------------------------------------------
@router.post(
    "/agent/rollback/confirm",
    response_model=ExecutionResponse,
    summary="Eksekusi Rollback Setelah Konfirmasi User",
)
@limiter.limit("20/minute")
async def confirm_rollback_plan(
    request: Request, payload: RollbackConfirmRequest
):
    plan_data = get_plan(payload.plan_id)

    # Validasi Keberadaan Plan & Jenis Aksi
    if not plan_data or plan_data.get("action") != "rollback":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Action plan rollback tidak ditemukan.",
        )

    # Pengecekan Jika Approved = False (Ditolak User)
    if not payload.approved:
        update_and_expire_plan(payload.plan_id, status="rejected_by_user")
        return ExecutionResponse(
            status="REJECTED",
            action="rollback",
            requires_confirmation=False,
            message="Permintaan rollback ditolak oleh user.",
            results=[],
        )

    # Pengecekan Masa Berlaku (Expired Check)
    if not is_plan_valid(plan_data):
        update_and_expire_plan(payload.plan_id, status="expired")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Action plan sudah kadaluwarsa (expired) atau sudah pernah digunakan.",
        )

    # Validasi Katalog untuk Mode Non-ALL
    target_catalogs = plan_data.get("catalogs", [])
    single_catalog_in_plan = plan_data.get("catalog")

    if single_catalog_in_plan:
        if (
            not payload.catalog
            or payload.catalog.upper() != single_catalog_in_plan.upper()
        ):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Parameter catalog tidak sesuai dengan Action Plan ({single_catalog_in_plan}).",
            )

    # Eksekusi Rollback & Update Plan Menjadi Expired
    execution_results: List[CatalogResult] = []

    for cat_id in target_catalogs:
        # Panggil task execution dengan action "rollback"
        res = run_taskfile(cat_id, "rollback")
        execution_results.append(res)

    # Tandai plan sebagai terpakai / expired
    update_and_expire_plan(payload.plan_id, status="executed")

    return ExecutionResponse(
        status="COMPLETED",
        action="rollback",
        requires_confirmation=False,
        message=f"Aksi 'rollback' selesai diproses untuk {len(execution_results)} katalog.",
        results=execution_results,
    )