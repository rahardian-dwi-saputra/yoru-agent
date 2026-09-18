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
    log_data: Optional[Dict[str, Any]] = None  # Menampung isi JSON log terakhir


class ExecutionResponse(BaseModel):
    status: str
    action: str
    requires_confirmation: bool = False
    message: str
    results: List[CatalogResult] = []