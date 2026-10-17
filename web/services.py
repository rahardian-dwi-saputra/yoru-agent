import sys
import os
import requests


CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.abspath(os.path.join(CURRENT_DIR, ".."))
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)

from config.api import API_HOST, API_PORT, API_KEY_PATH

from database import (
    DB_PATH,
    init_db,
    get_paginated_catalogs,
    save_or_update_catalogs,
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
            f"{API_BASE_URL}/system/info", headers=headers, timeout=3
        )

        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    
    return {
        "os_platform": "",
        "architecture": "x86_64",
    }


def fetch_catalog_data(page: int = 1, per_page: int = 10):
    """Menarik daftar katalog dari endpoint /catalogs dan menyimpannya ke database lokal."""

    api_key = get_api_key()
    
    headers = {}
    if api_key:
        headers["X-API-Key"] = api_key

    try:
        response = requests.get(
            f"{API_BASE_URL}/catalogs", headers=headers, timeout=5
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
            f"{API_BASE_URL}/catalogs", headers=headers, timeout=5
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