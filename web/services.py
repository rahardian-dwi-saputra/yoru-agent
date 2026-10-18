import sys
import os
import requests
from datetime import datetime


CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from config.api import API_HOST, API_PORT, API_KEY_PATH

from database import (
    init_db,
    get_paginated_catalogs,
    save_or_update_catalogs,
    update_execution_status,
    get_dashboard_metrics,
)

API_BASE_URL = f"http://{API_HOST}:{API_PORT}/api/v1"

init_db()

def get_api_key() -> str:
    """Membaca isi file API key dari path yang ditentukan di config/api.py."""
    # Jika path bersifat relatif, ubah menjadi absolut berdasarkan root proyek
    full_key_path = (
        API_KEY_PATH
        if os.path.isabs(API_KEY_PATH)
        else os.path.join(PROJECT_DIR, API_KEY_PATH)
    )

    try:
        if os.path.exists(full_key_path):
            with open(full_key_path, "r", encoding="utf-8") as f:
                return f.read().strip()
    except Exception:
        pass
    return ""


def fetch_system_info():
    """Mengambil informasi Sistem dari FastAPI."""
    api_key = get_api_key()

    headers = {}
    if api_key:
        headers["X-API-Key"] = api_key

    try:
        response = requests.get(
            f"{API_BASE_URL}/system/info", 
            headers=headers, 
            timeout=3
        )

        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    
    return {
        "os_platform": "",
        "architecture": "",
    }


def fetch_catalog_data(page: int = 1, per_page: int = 10):
    """Menarik daftar katalog dari endpoint /catalogs dan menyimpannya ke database lokal."""

    api_key = get_api_key()
    
    headers = {}
    if api_key:
        headers["X-API-Key"] = api_key

    try:
        response = requests.get(
            f"{API_BASE_URL}/catalogs", 
            headers=headers, 
            timeout=5
        )

        if response.status_code == 200:
            data = response.json()
            catalogs_list = data.get("catalogs", [])

            if catalogs_list:
                save_or_update_catalogs(catalogs_list)

    except Exception:
        pass

    return get_paginated_catalogs(page=page, per_page=per_page)


def fetch_dashboard_metrics():
    """Mengambil metrik statistik dari database lokal dan memformatnya

    untuk rasio Total Audit dan Total Hardening.
    """
    try:
        metrics = get_dashboard_metrics()
        
        total_audit_roles = metrics.get("total_audit_roles", 0)
        total_audit_berhasil = metrics.get("total_audit_berhasil", 0)
        
        total_hardening_roles = metrics.get("total_hardening_roles", 0)
        total_hardening_berhasil = metrics.get("total_hardening_berhasil", 0)

        total_rollback_roles = metrics.get("total_rollback_roles", 0)
        total_rollback_berhasil = metrics.get("total_rollback_berhasil", 0)
        
        return {
            "audit_ratio": f"{total_audit_berhasil} / {total_audit_roles}",
            "hardening_ratio": f"{total_hardening_berhasil} / {total_hardening_roles}",
            "rollback_ratio": f"{total_rollback_berhasil} / {total_rollback_roles}",
            "raw": metrics
        }
    except Exception:
        pass
    
    # Fallback jika terjadi kendala
    return {
        "audit_ratio": "0 / 0",
        "hardening_ratio": "0 / 0",
        "rollback_ratio": "0 / 0",
        "raw": {}
    }


def refresh_catalog_data():
    """Memaksa penarikan data katalog terbaru dari endpoint /catalogs

    dan memperbarui database lokal SQLite. Mengembalikan True jika berhasil.
    """
    api_key = get_api_key()
    headers = {}
    if api_key:
        headers["X-API-Key"] = api_key

    try:
        response = requests.get(
            f"{API_BASE_URL}/catalogs", 
            headers=headers, 
            timeout=5
        )
        if response.status_code == 200:
            data = response.json()
            catalogs_list = data.get("catalogs", [])
            if catalogs_list:
                save_or_update_catalogs(catalogs_list)
                return True
    except Exception:
        pass
    return False


def trigger_audit_all():
    """Mengirim request POST /agent/audit untuk seluruh katalog ('ALL'),

    lalu memperbarui status audit dan waktu audit menggunakan update_execution_status.
    """
    api_key = get_api_key()
    headers = {"X-API-Key": api_key, "Content-Type": "application/json"} if api_key else {"Content-Type": "application/json"}
    payload = {"catalogs": ["ALL"]}

    try:
        response = requests.post(
            f"{API_BASE_URL}/agent/audit", 
            headers=headers, 
            json=payload, 
            timeout=30
        )
        if response.status_code == 200:
            data = response.json()
            results = data.get("results", [])

            if results:
                current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                for res in results:
                    catalog_id = res.get("catalog")
                    log_data = res.get("log_data", {})
                    
                    if catalog_id and log_data:
                        audit_level = log_data.get("level", "PENDING")
                        
                        update_execution_status(
                            rule_id=catalog_id,
                            action_type="audit",
                            status=audit_level,
                            timestamp=current_time
                        )

            return True, data.get("message", "Audit selesai diproses.")
    except Exception as e:
        pass
    
    return False, "Gagal menghubungi endpoint /agent/audit."


def trigger_single_audit(rule_id: str):
    """Mengirim request POST /agent/audit untuk satu katalog tertentu,

    lalu memperbarui status audit dan waktu audit menggunakan update_execution_status.
    """
    api_key = get_api_key()
    headers = {"X-API-Key": api_key, "Content-Type": "application/json"} if api_key else {"Content-Type": "application/json"}
    payload = {"catalogs": [rule_id]}

    try:
        response = requests.post(
            f"{API_BASE_URL}/agent/audit", 
            headers=headers, 
            json=payload, 
            timeout=30
        )
        if response.status_code == 200:
            data = response.json()
            results = data.get("results", [])

            if results:
                current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                for res in results:
                    catalog_id = res.get("catalog")
                    log_data = res.get("log_data", {})
                    
                    if catalog_id and log_data:
                        audit_level = log_data.get("level", "PENDING")
                        
                        update_execution_status(
                            rule_id=catalog_id,
                            action_type="audit",
                            status=audit_level,
                            timestamp=current_time
                        )

            return True, data.get(
                "message", f"Audit untuk rule {rule_id} selesai diproses."
            )
    except Exception:
        pass
    
    return False, f"Gagal menjalankan audit untuk rule {rule_id}."


def init_hardening_all():
    """Meminta plan hardening untuk seluruh katalog (/agent/hardening/init)."""
    api_key = get_api_key()
    headers = {"X-API-Key": api_key, "Content-Type": "application/json"} if api_key else {"Content-Type": "application/json"}
    payload = {"catalogs": ["ALL"]}

    try:
        response = requests.post(
            f"{API_BASE_URL}/agent/hardening/init", 
            headers=headers, 
            json=payload, 
            timeout=30
        )
        if response.status_code == 200:
            return True, response.json()
    except Exception:
        pass
    return False, {"message": "Gagal menghubungi endpoint /agent/hardening/init."}


def init_single_hardening(rule_id: str):
    """Meminta plan hardening untuk satu katalog tertentu (/agent/hardening/init)."""
    api_key = get_api_key()
    headers = {"X-API-Key": api_key, "Content-Type": "application/json"} if api_key else {"Content-Type": "application/json"}
    payload = {"catalogs": [rule_id]}

    try:
        response = requests.post(
            f"{API_BASE_URL}/agent/hardening/init", 
            headers=headers, 
            json=payload, 
            timeout=30
        )
        if response.status_code == 200:
            return True, response.json()
    except Exception:
        pass
    return False, {"message": f"Gagal menginisialisasi plan hardening untuk rule {rule_id}."}


def confirm_hardening_plan(plan_id: str, approved: bool, catalog: str = None):
    """Mengirim konfirmasi persetujuan atau pembatalan plan hardening (/agent/hardening/confirm)."""
    api_key = get_api_key()
    headers = {"X-API-Key": api_key, "Content-Type": "application/json"} if api_key else {"Content-Type": "application/json"}
    payload = {"plan_id": plan_id, "approved": approved}

    if catalog:
        payload["catalog"] = catalog

    try:
        response = requests.post(
            f"{API_BASE_URL}/agent/hardening/confirm", 
            headers=headers, 
            json=payload, 
            timeout=60
        )
        if response.status_code == 200:
            data = response.json()
            
            # Jika disetujui (approved=True), lakukan update status ke database lokal
            if approved and "results" in data:
                current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                for res in data.get("results", []):
                    catalog_id = res.get("catalog")
                    log_data = res.get("log_data", {})
                    
                    if catalog_id and log_data:

                        hardening_level = log_data.get("level", "PENDING")
                        
                        update_execution_status(
                            rule_id=catalog_id,
                            action_type="hardening",
                            status=hardening_level,
                            timestamp=current_time
                        )
                        
            return True, data
    except Exception:
        pass
    
    return False, {"message": "Gagal menghubungi endpoint /agent/hardening/confirm."}


def init_rollback_all():
    """Meminta plan rollback untuk seluruh katalog (/agent/rollback/init)."""
    api_key = get_api_key()
    headers = {"X-API-Key": api_key, "Content-Type": "application/json"} if api_key else {"Content-Type": "application/json"}
    payload = {"catalogs": ["ALL"]}

    try:
        response = requests.post(
            f"{API_BASE_URL}/agent/rollback/init", headers=headers, json=payload, timeout=30
        )
        if response.status_code == 200:
            return True, response.json()
    except Exception:
        pass
    return False, {"message": "Gagal menghubungi endpoint /agent/rollback/init."}


def init_single_rollback(rule_id: str):
    """Meminta plan rollback untuk satu katalog tertentu (/agent/rollback/init)."""
    api_key = get_api_key()
    headers = {"X-API-Key": api_key, "Content-Type": "application/json"} if api_key else {"Content-Type": "application/json"}
    payload = {"catalogs": [rule_id]}

    try:
        response = requests.post(
            f"{API_BASE_URL}/agent/rollback/init", headers=headers, json=payload, timeout=30
        )
        if response.status_code == 200:
            return True, response.json()
    except Exception:
        pass
    return False, {"message": f"Gagal menginisialisasi plan rollback untuk rule {rule_id}."}


def confirm_rollback_plan(plan_id: str, approved: bool, catalog: str = None):
    """Mengirim konfirmasi persetujuan atau pembatalan plan rollback (/agent/rollback/confirm)."""
    api_key = get_api_key()
    headers = {"X-API-Key": api_key, "Content-Type": "application/json"} if api_key else {"Content-Type": "application/json"}
    payload = {"plan_id": plan_id, "approved": approved}

    if catalog:
        payload["catalog"] = catalog

    try:
        response = requests.post(
            f"{API_BASE_URL}/agent/rollback/confirm", headers=headers, json=payload, timeout=60
        )
        if response.status_code == 200:
            data = response.json()
            
            # Jika disetujui (approved=True), update status rollback ke database lokal
            if approved and "results" in data:
                current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                for res in data.get("results", []):
                    catalog_id = res.get("catalog")
                    log_data = res.get("log_data", {})
                    
                    if catalog_id and log_data:
                        rollback_level = log_data.get("level", "PENDING") # Contoh: SUCCESS / FAILED
                        
                        # Memanggil fungsi database yang sudah ada
                        update_execution_status(
                            rule_id=catalog_id,
                            action_type="rollback",
                            status=rollback_level,
                            timestamp=current_time
                        )
                        
            return True, data
    except Exception:
        pass
    
    return False, {"message": "Gagal menghubungi endpoint /agent/rollback/confirm."}