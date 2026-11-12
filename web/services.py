from __future__ import annotations
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote
import sys
import requests


CURRENT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = CURRENT_DIR.parent

if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

from config.api import API_HOST, API_PORT, API_KEY_PATH

from database import (
    init_db,
    get_paginated_catalogs,
    save_or_update_catalogs,
    update_execution_status,
    get_dashboard_metrics,
    save_server_info,
)

API_BASE_URL = f"http://{API_HOST}:{API_PORT}/api/v1"

REQUEST_TIMEOUT = 10
ACTION_TIMEOUT = 30
CONFIRM_TIMEOUT = 60

ALL_ACTION_TIMEOUT = 600       
ALL_CONFIRM_TIMEOUT = 180 


def get_api_key() -> str:
    """Membaca API key dari file konfigurasi."""
    key_path = Path(API_KEY_PATH)
    if not key_path.is_absolute():
        key_path = PROJECT_DIR / key_path

    try:
        return key_path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        return ""
    except OSError:
        return ""


def _get_headers(*, json_content: bool = False) -> dict[str, str]:
    """Membuat header request dan menyertakan API key jika tersedia."""
    headers = {}
    api_key = get_api_key()

    if api_key:
        headers["X-API-Key"] = api_key
    if json_content:
        headers["Content-Type"] = "application/json"

    return headers


def _request(
    method: str,
    endpoint: str,
    *,
    payload: dict[str, Any] | None = None,
    timeout: int = REQUEST_TIMEOUT,
) -> tuple[bool, dict[str, Any], str]:
    """
    Menjalankan request ke API.

    Return: (berhasil, response_json, pesan_error).
    """
    url = f"{API_BASE_URL}{endpoint}"

    try:
        response = requests.request(
            method=method,
            url=url,
            headers=_get_headers(json_content=payload is not None),
            json=payload,
            timeout=timeout,
        )
    except requests.Timeout:
        return False, {}, f"Request ke {endpoint} mengalami timeout."
    except requests.RequestException as exc:
        return False, {}, f"Tidak dapat menghubungi API ({endpoint}): {exc}"

    if not response.ok:
        detail = response.text.strip()[:500]
        message = f"API mengembalikan HTTP {response.status_code}"
        if detail:
            message += f": {detail}"
        return False, {}, message

    if not response.content:
        return True, {}, ""

    try:
        data = response.json()
    except requests.exceptions.JSONDecodeError:
        return False, {}, f"Respons API {endpoint} bukan JSON yang valid."

    if not isinstance(data, dict):
        return False, {}, f"Format respons API {endpoint} tidak sesuai."

    return True, data, ""


def _update_result_status(results: list[dict[str, Any]], action_type: str) -> None:
    """Menyimpan status setiap hasil eksekusi ke database lokal."""
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for result in results:
        if not isinstance(result, dict):
            continue

        catalog_id = result.get("catalog")
        log_data = result.get("log_data") or {}

        if not catalog_id or not isinstance(log_data, dict):
            continue

        status = log_data.get("status")

        if not status:
            continue

        message = log_data.get("message") or "-"

        update_execution_status(
            rule_id=str(catalog_id),
            action_type=action_type,
            status=str(status).upper(),
            timestamp=timestamp,
            message=message,
        )


def _trigger_audit(catalogs: list[str]) -> tuple[bool, str]:
    """Menjalankan audit untuk satu atau beberapa katalog."""

    timeout = (
        ALL_ACTION_TIMEOUT
        if catalogs == ["ALL"]
        else ACTION_TIMEOUT
    )

    success, data, error = _request(
        "POST",
        "/agent/audit",
        payload={"catalogs": catalogs},
        timeout=timeout,
    )
    if not success:
        return False, error

    results = data.get("results", [])
    if isinstance(results, list):
        _update_result_status(results, "audit")

    return True, data.get("message", "Audit selesai diproses.")


def _init_plan(
    action: str,
    catalogs: list[str],
) -> tuple[bool, dict[str, Any]]:
    """Meminta plan hardening atau rollback ke API."""
    endpoint = f"/agent/{action}/init"

    timeout = (
        ALL_ACTION_TIMEOUT
        if catalogs == ["ALL"]
        else ACTION_TIMEOUT
    )

    success, data, error = _request(
        "POST",
        endpoint,
        payload={"catalogs": catalogs},
        timeout=timeout,
    )

    if not success:
        return False, {"message": error}

    return True, data


def _confirm_plan(
    action: str,
    plan_id: str,
    approved: bool,
    catalog: str | None = None,
) -> tuple[bool, dict[str, Any]]:
    """Mengirim keputusan plan dan menyinkronkan status melalui audit."""
    payload: dict[str, Any] = {
        "plan_id": plan_id,
        "approved": approved,
    }

    if catalog:
        payload["catalog"] = catalog

    endpoint = f"/agent/{action}/confirm"
    timeout = ALL_CONFIRM_TIMEOUT if catalog is None else CONFIRM_TIMEOUT

    success, data, error = _request(
        "POST",
        endpoint,
        payload=payload,
        timeout=timeout,
    )

    if not success:
        return False, {"message": error}

    if not approved:
        return True, data

    results = data.get("results", [])
    if isinstance(results, list):
        _update_result_status(results, action)

    # Sinkronisasi status setelah hardening atau rollback.
    if action in {"hardening", "rollback"}:
        audit_catalogs = ["ALL"] if catalog is None else [catalog]
        audit_success, audit_message = _trigger_audit(audit_catalogs)

        data["audit_sync"] = {
            "success": audit_success,
            "message": audit_message,
        }

        if audit_success:
            data["message"] = (
                f"{data.get('message', 'Proses selesai.')}"
                " Sinkronisasi status melalui audit berhasil."
            )
        else:
            data["message"] = (
                f"{data.get('message', 'Proses selesai.')}"
                f" Namun, sinkronisasi audit gagal: {audit_message}"
            )

    return True, data


def fetch_system_info() -> dict[str, Any]:
    """Mengambil dan menyimpan informasi sistem dari FastAPI."""

    success, data, _ = _request("GET", "/system/info", timeout=3)

    if not success:
        return {
            "os_platform": "",
            "architecture": "",
            "hostname": "",
        }

    system_info = {
        "os_platform": data.get("os_platform", ""),
        "architecture": data.get("architecture", ""),
        "hostname": data.get("hostname", ""),
    }

    save_server_info(system_info)

    return system_info


def fetch_catalog_data(
    page: int = 1,
    per_page: int = 10,
) -> tuple[list[dict[str, Any]], int]:
    """
    Mengambil katalog dari API, menyimpannya ke SQLite, lalu
    mengembalikan data lokal sesuai pagination.
    """
    success, data, _ = _request("GET", "/catalogs", timeout=REQUEST_TIMEOUT)

    if success:
        catalogs = data.get("catalogs", [])
        if isinstance(catalogs, list) and catalogs:
            system_info = fetch_system_info()
            save_or_update_catalogs(catalogs, server_info=system_info)

    return get_paginated_catalogs(page=page, per_page=per_page)


def fetch_dashboard_metrics() -> dict[str, Any]:
    """Mengambil metrik SQLite dan memformatnya untuk dashboard."""
    metrics = get_dashboard_metrics()

    audit_done = metrics.get("total_audit_berhasil", 0)
    audit_total = metrics.get("total_audit_roles", 0)
    hardening_done = metrics.get("total_hardening_berhasil", 0)
    hardening_total = metrics.get("total_hardening_roles", 0)
    rollback_done = metrics.get("total_rollback_berhasil", 0)
    rollback_total = metrics.get("total_rollback_roles", 0)

    return {
        "audit_ratio": f"{audit_done} / {audit_total}",
        "hardening_ratio": f"{hardening_done} / {hardening_total}",
        "rollback_ratio": f"{rollback_done} / {rollback_total}",
        "raw": metrics,
    }


def refresh_catalog_data() -> bool:
    """Memperbarui cache katalog lokal dari API."""
    success, data, _ = _request("GET", "/catalogs", timeout=REQUEST_TIMEOUT)
    if not success:
        return False

    catalogs = data.get("catalogs", [])
    if not isinstance(catalogs, list):
        return False

    # Respons sukses dengan daftar kosong tetap dianggap berhasil.
    if catalogs:
        system_info = fetch_system_info()
        save_or_update_catalogs(catalogs, server_info=system_info)

    return True


def trigger_audit_all() -> tuple[bool, str]:
    """Menjalankan audit untuk seluruh katalog."""
    return _trigger_audit(["ALL"])


def trigger_single_audit(rule_id: str) -> tuple[bool, str]:
    """Menjalankan audit untuk satu katalog."""
    return _trigger_audit([rule_id])


def init_hardening_all() -> tuple[bool, dict[str, Any]]:
    """Membuat plan hardening untuk seluruh katalog."""
    return _init_plan("hardening", ["ALL"])


def init_single_hardening(rule_id: str) -> tuple[bool, dict[str, Any]]:
    """Membuat plan hardening untuk satu katalog."""
    return _init_plan("hardening", [rule_id])


def confirm_hardening_plan(
    plan_id: str,
    approved: bool,
    catalog: str | None = None,
) -> tuple[bool, dict[str, Any]]:
    """Menyetujui atau membatalkan plan hardening."""
    return _confirm_plan("hardening", plan_id, approved, catalog)


def init_rollback_all() -> tuple[bool, dict[str, Any]]:
    """Membuat plan rollback untuk seluruh katalog."""
    return _init_plan("rollback", ["ALL"])


def init_single_rollback(rule_id: str) -> tuple[bool, dict[str, Any]]:
    """Membuat plan rollback untuk satu katalog."""
    return _init_plan("rollback", [rule_id])


def confirm_rollback_plan(
    plan_id: str,
    approved: bool,
    catalog: str | None = None,
) -> tuple[bool, dict[str, Any]]:
    """Menyetujui atau membatalkan plan rollback."""
    return _confirm_plan("rollback", plan_id, approved, catalog)


def fetch_catalog_logs(
    catalog_id: str,
    log_type: str,
) -> tuple[bool, list[dict[str, Any]], str]:
    """Mengambil riwayat log audit, hardening, atau rollback suatu katalog."""

    allowed_types = {"audit", "hardening", "rollback"}

    if log_type not in allowed_types:
        return False, [], f"Jenis log tidak valid: {log_type}"

    if not catalog_id or not catalog_id.strip():
        return False, [], "ID katalog tidak boleh kosong."

    endpoint = (
        f"/logs/{quote(catalog_id.strip(), safe='')}"
        f"/{log_type}"
    )

    success, response, error = _request(
        "GET",
        endpoint,
        timeout=REQUEST_TIMEOUT,
    )

    if not success:
        return False, [], error

    logs = response.get("data", [])

    if not isinstance(logs, list):
        return False, [], "Format data log dari API tidak sesuai."

    logs = [log for log in logs if isinstance(log, dict)]

    return True, logs, ""


def fetch_catalog_ai_advice(
    catalog_id: str
) -> tuple[bool, dict[str, Any], str]:
    """
    Meminta nasehat/analisis AI untuk katalog tertentu (K01/K02/dst)
    berdasarkan file log audit, hardening, dan rollback yang tersedia.
    """
    if not catalog_id or not catalog_id.strip():
        return False, {}, "ID katalog tidak boleh kosong."

    endpoint = f"/ai-advisor/advice/{quote(catalog_id.strip(), safe='')}"

    success, response, error = _request(
        "GET",
        endpoint,
        timeout=80,
    )

    if not success:
        return False, {}, error

    return True, response, ""


def fetch_global_log_summary() -> tuple[bool, dict[str, Any], str]:
    """
    Meminta ringkasan eksekutif (executive summary) global 
    dari seluruh log katalog yang ada di server.
    """
    endpoint = "/ai-advisor/summary/all"

    success, response, error = _request(
        "GET",
        endpoint,
        timeout=200,
    )

    if not success:
        return False, {}, error

    return True, response, ""


# Inisialisasi database ketika modul service pertama kali dimuat.
init_db()