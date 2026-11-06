from __future__ import annotations

import json
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Request, Path as FastPath, status

from api.config import limiter
from api.dependencies import verify_api_key
from config.api import CATALOGS_DIR

ALLOWED_LOG_TYPES = {"audit", "hardening", "rollback"}

router = APIRouter(
    prefix="/api/v1/logs", 
    tags=["Logs Manager"],
    dependencies=[Depends(verify_api_key)]
)


@router.get(
    "/{catalog_id}/{log_type}", 
    response_model=Dict[str, Any],
    summary="Mendapatkan isi log spesifik",
)
@limiter.limit("10/minute")
def get_catalog_log(
    request: Request,
    catalog_id: str = FastPath(..., description="ID Katalog, contoh: K01, K10"),
    log_type: str = FastPath(..., description="Jenis log: audit, hardening, atau rollback"),
) -> Dict[str, Any]:
    """
    Membaca file log tertentu (audit.json, hardening.json, atau rollback.json) 
    berdasarkan ID katalog.
    """
    normalized_log_type = log_type.lower()
    if normalized_log_type not in ALLOWED_LOG_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Jenis log tidak valid. Pilih dari: {', '.join(ALLOWED_LOG_TYPES)}",
        )

    log_file_path = CATALOGS_DIR / catalog_id.upper() / "logs" / f"{normalized_log_type}.json"

    if not log_file_path.is_file():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"File log '{normalized_log_type}.json' untuk katalog {catalog_id.upper()} tidak ditemukan.",
        )

    try:
        log_data = []
        with open(log_file_path, "r", encoding="utf-8") as f:
            for line in f:
                stripped_line = line.strip()
                if stripped_line:
                    log_data.append(json.loads(stripped_line))

        return {
            "catalog": catalog_id.upper(),
            "log_type": normalized_log_type,
            "data": log_data,
        }
    except json.JSONDecodeError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"Format file JSON rusak atau tidak valid: {exc}"
        )
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"Terjadi kesalahan saat membaca file log: {exc}"
        )


@router.get(
    "/{catalog_id}",
    response_model=Dict[str, Any],
    summary="Mendapatkan semua log dalam satu katalog",
)
@limiter.limit("10/minute")
def get_all_catalog_logs(
    request: Request,
    catalog_id: str = FastPath(..., description="ID Katalog, contoh: K01"),
) -> Dict[str, Any]:
    """
    Membaca seluruh file log (audit, hardening, rollback) 
    yang tersedia untuk katalog tertentu sekaligus.
    """
    catalog_dir = CATALOGS_DIR / catalog_id.upper() / "logs"

    if not catalog_dir.exists() or not catalog_dir.is_dir():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Direktori log untuk katalog {catalog_id.upper()} tidak ditemukan.",
        )

    result = {}
    for l_type in ALLOWED_LOG_TYPES:
        file_path = catalog_dir / f"{l_type}.json"
        if file_path.is_file():
            try:
                lines_data = []
                with open(file_path, "r", encoding="utf-8") as f:
                    for line in f:
                        stripped_line = line.strip()
                        if stripped_line:
                            lines_data.append(json.loads(stripped_line))
                result[l_type] = lines_data
            except Exception:
                result[l_type] = {"error": "Gagal mem-parsing file log."}
        else:
            result[l_type] = None
            
    return {
        "catalog": catalog_id.upper(),
        "logs": result,
    }