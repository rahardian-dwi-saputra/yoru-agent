from __future__ import annotations
from fastapi import APIRouter, HTTPException, Depends, Request, status
import os
import json
from typing import Any, Dict
from google import genai
from google.genai import types
from api.config import limiter
from api.dependencies import verify_api_key
from config.api import CATALOGS_DIR


router = APIRouter(
    prefix="/ai-advisor", 
    tags=["AI Advisor & Summarizer"],
    dependencies=[Depends(verify_api_key)]
)


def read_log_file(filename: str, catalog_id: str) -> list[dict]:
    """
    Membaca file log berdasarkan katalog, mencari execution_id terbaru,
    dan mengembalikan seluruh catatan log yang memiliki execution_id yang sama.
    """

    log_file = CATALOGS_DIR / catalog_id.upper() / "logs" / filename

    if not os.path.exists(log_file):
        return []

    try:
        with open(log_file, "r", encoding="utf-8") as f:
            logs = json.load(f)

        if not isinstance(logs, list) or not logs:
            return []

        # 1. Cari log dengan timestamp terbaru untuk mendapatkan execution_id terakhir
        sorted_logs = sorted(
            logs, 
            key=lambda x: x.get("timestamp", ""), 
            reverse=True
        )
        
        latest_execution_id = sorted_logs[0].get("execution_id")

        if not latest_execution_id:
            return []

        # 2. Ambil semua log yang memiliki execution_id yang sama dengan eksekusi terbaru
        latest_session_logs = [
            log for log in logs 
            if log.get("execution_id") == latest_execution_id
        ]

        return latest_session_logs

    except Exception as e:
        print(f"[ERROR] Gagal membaca file log {filename} untuk {catalog_id}: {e}")
        return []


@router.get(
    "/advice/{catalog_id}",
    response_model=Dict[str, Any],
    summary="Mendapatkan nasehat AI untuk katalog tertentu",
)
@limiter.limit("20/minute")
def get_catalog_ai_advice(
    request: Request,
    catalog_id: str
) -> Dict[str, Any]:
    """
    Endpoint khusus meminta nasehat AI untuk katalog tertentu (K01/K02/dst)
    berdasarkan file log audit, hardening, dan rollback yang tersedia.
    """

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="GEMINI_API_KEY belum dikonfigurasi di environment."
        )
    
    audit_data = read_log_file("audit.json", catalog_id)
    hardening_data = read_log_file("hardening.json", catalog_id)
    rollback_data = read_log_file("rollback.json", catalog_id)

    if not audit_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail=f"Log audit wajib (audit.json) untuk katalog {catalog_id} tidak ditemukan."
        )
   
    client = genai.Client(api_key=api_key)
    prompt = f"""
    Anda adalah Senior Security Engineering Copilot untuk Yoru-Agent.
    Analisis status kontrol keamanan untuk katalog {catalog_id} berdasarkan data berikut:
    - Audit Log (Wajib): {json.dumps(audit_data, indent=2)}
    - Hardening Log (Opsional/Jika ada): {json.dumps(hardening_data, indent=2) if hardening_data else "Belum ada riwayat hardening"}
    - Rollback Log (Opsional/Jika ada): {json.dumps(rollback_data, indent=2) if rollback_data else "Belum ada riwayat rollback"}

    Berikan saran keamanan, analisis akar masalah (jika ditemukan error pada audit/hardening), dan rekomendasi mitigasi dalam format JSON murni:
    {{"summary": "...", "root_cause": "...", "recommendation": "..."}}
    """

    try:
        response = client.models.generate_content(
            model='gemini-3.8-flash',
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json", 
                temperature=0.2
            ),
        )
        ai_result = json.loads(response.text)
    except Exception as e:
        ai_result = {
            "summary": "Gagal memproses analisis AI.",
            "root_cause": str(e),
            "recommendation": "Tinjau file log secara manual."
        }
        
    response = client.models.generate_content(
        model='gemini-3.8-flash',
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json", temperature=0.2),
    )
    
    return {
        "catalog_id": catalog_id.upper(),
        "available_logs": {
            "audit": True,
            "hardening": bool(hardening_data),
            "rollback": bool(rollback_data)
        },
        "ai_advice": ai_result
    }


@router.get(
    "/summary/all",
    response_model=Dict[str, Any],
    summary="Mendapatkan nasehat AI untuk seluruh log katalog secara global",
)
@limiter.limit("10/minute")
def get_global_log_summary(
    request: Request,
) -> Dict[str, Any]:
    """
    Endpoint khusus meringkas hasil log dari seluruh katalog secara global:
    - Memindai semua katalog di CATALOGS_DIR.
    - Mengambil log audit terbaru (Wajib).
    - Menyertakan log hardening & rollback jika ada (Opsional).
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="GEMINI_API_KEY belum dikonfigurasi di environment."
        )
    
    if not CATALOGS_DIR.exists():
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, 
            detail="Direktori katalog (CATALOGS_DIR) tidak ditemukan."
        )

    catalog_dirs = [d.name for d in CATALOGS_DIR.iterdir() if d.is_dir()]

    if not catalog_dirs:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Belum ada direktori katalog yang tersedia."
        )

    global_summary_data = []

    for cat_id in sorted(catalog_dirs):
        audit_logs = read_log_file("audit.json", cat_id)

        if not audit_logs:
            continue

        hardening_logs = read_log_file("hardening.json", cat_id)
        rollback_logs = read_log_file("rollback.json", cat_id)

        global_summary_data.append({
            "catalog_id": cat_id,
            "latest_audit": audit_logs,
            "latest_hardening": hardening_logs if hardening_logs else "Tidak ada riwayat hardening",
            "latest_rollback": rollback_logs if rollback_logs else "Tidak ada riwayat rollback"
        })

    
    if not global_summary_data:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Belum ada data log audit yang valid untuk diringkas dari seluruh katalog."
        )


    client = genai.Client(api_key=api_key)
    
    prompt = f"""
    Anda adalah Senior Security Auditor. Buat ringkasan eksekutif (executive summary) yang komprehensif dari keseluruhan status server berdasarkan data log multi-katalog berikut:
    {json.dumps(global_summary_data, indent=2)}

    Berikan analisis profesional mengenai:
    1. Tingkat kepatuhan server secara keseluruhan.
    2. Area atau katalog kontrol keamanan yang masih berisiko tinggi (status FAILED/ERROR).
    3. Langkah prioritas perbaikan selanjutnya bagi administrator.
    """

    try:
        response = client.models.generate_content(
            model='gemini-3.8-flash',
            contents=prompt,
        )
        executive_summary_text = response.text
    except Exception as e:
        raise HTTPException(
            status_code=500, 
            detail=f"Gagal menghasilkan ringkasan AI: {str(e)}"
        )

    return {
        "mode": "global_summary",
        "total_catalogs_analyzed": len(global_summary_data),
        "executive_summary": executive_summary_text
    }
    