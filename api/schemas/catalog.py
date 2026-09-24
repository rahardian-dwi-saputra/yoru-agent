from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field


class CatalogMetadata(BaseModel):
    id: str
    nama: str
    kode_cis: str
    cis_judul: str
    deskripsi: Optional[str] = ""
    resiko: str
    kategori: str
    audit_only: bool = Field(
        default=False, 
        description="Indikator apakah katalog ini hanya mengizinkan audit tanpa hardening/rollback."
    )


class CatalogListResponse(BaseModel):
    total: int
    catalogs: List[CatalogMetadata]


class AuditRequest(BaseModel):
    catalogs: List[str] = Field(
        ...,
        description="Daftar ID Katalog (misal ['K01', 'K03']) atau ['ALL'] untuk semua katalog.",
        examples=[["K01", "K02"]],
    )


class CatalogResult(BaseModel):
    catalog: str
    status: Literal["SUCCESS", "FAILED", "SKIPPED", "CANCELLED"]
    output: str
    error: Optional[str] = None
    log_data: Optional[Dict[str, Any]] = None


class ExecutionResponse(BaseModel):
    status: str
    action: str
    requires_confirmation: bool = False
    message: str
    results: List[CatalogResult] = []


# Schema Khusus Hardening
class HardeningInitRequest(BaseModel):
    catalogs: List[str] = Field(
        ...,
        description="Daftar ID Katalog (misal ['K01', 'K02']) atau ['ALL'].",
        examples=[["ALL"], ["K01", "K02"]],
    )

class HardeningConfirmRequest(BaseModel):
    plan_id: str = Field(..., description="ID Plan yang didapat dari server.")
    approved: bool = Field(
        ..., description="Konfirmasi persetujuan (True/False)."
    )
    catalog: Optional[str] = Field(
        default=None,
        description="Indeks katalog (K01/K02/K03) wajib diisi untuk single/multi non-ALL.",
    )


class HardeningPlanItem(BaseModel):
    plan_id: str
    status: str
    expires_at: str
    catalogs: List[str]
    catalog: Optional[str] = None


class HardeningInitResponse(BaseModel):
    status: str
    message: str
    is_all_mode: bool
    plans: List[HardeningPlanItem]


# Schema Khusus Rollback
class RollbackInitRequest(BaseModel):
    catalogs: List[str] = Field(
        ...,
        description="Daftar ID Katalog (misal ['K01', 'K02']) atau ['ALL'].",
        examples=[["ALL"], ["K01", "K02"]],
    )


class RollbackConfirmRequest(BaseModel):
    plan_id: str = Field(..., description="ID Plan yang didapat dari server (prefix rp-).")
    approved: bool = Field(
        ..., description="Konfirmasi persetujuan (True/False)."
    )
    catalog: Optional[str] = Field(
        default=None,
        description="Indeks katalog (K01/K02/K03) wajib diisi untuk single/multi non-ALL.",
    )


class ActionPlanItem(BaseModel):
    plan_id: str
    status: str
    expires_at: str
    catalogs: List[str]
    catalog: Optional[str] = None


class ActionPlanInitResponse(BaseModel):
    status: str
    message: str
    is_all_mode: bool
    plans: List[ActionPlanItem]