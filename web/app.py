from __future__ import annotations
from pathlib import Path
from dotenv import load_dotenv

import streamlit as st
import os
import hmac

from components import (
    render_catalog_table,
    render_control_bar,
    render_metrics_row,
    render_styles,
)

from services import (
    fetch_catalog_data, 
    fetch_system_info, 
    fetch_dashboard_metrics
)

from database import save_server_info

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


PAGE_TITLE = "Yoru-Agent Security Dashboard"
PAGE_ICON = "🛡️"
PAGE_SIZE = 10

DASHBOARD_PASSWORD = os.getenv("DASHBOARD_PASSWORD", "")


# Autentikasi

def require_login() -> bool:
    """Melindungi dashboard menggunakan password administrator."""

    if st.session_state.get("authenticated", False):
        return True

    st.title("🛡️ Yoru-Agent")
    st.subheader("Login Dashboard")
    st.caption("Masukkan password untuk mengakses dashboard.")
    st.divider()

    if not DASHBOARD_PASSWORD:
        st.error(
            "Password dashboard belum dikonfigurasi. "
            "Silakan atur DASHBOARD_PASSWORD pada file .env."
        )
        return False

    with st.form("login_form"):
        password = st.text_input(
            "Password",
            type="password",
            placeholder="Masukkan password administrator",
        )

        submitted = st.form_submit_button(
            "Login",
            use_container_width=True,
        )

    if submitted:
        if hmac.compare_digest(password, DASHBOARD_PASSWORD):
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Password tidak valid.")

    return False


def logout() -> None:
    """Mengakhiri sesi login dashboard."""

    st.session_state["authenticated"] = False
    st.rerun()

# Informasi Server

def initialize_server_info():
    """Mengambil informasi server sekali setiap sesi Streamlit."""

    if "server_info" not in st.session_state:
        server_info = fetch_system_info()

        st.session_state.server_info = server_info

        if server_info:
            save_server_info(server_info)

    return st.session_state.server_info


# Data Dashboard
def _load_dashboard_data(page: int) -> tuple[dict, list[dict], int, dict]:
    """Mengambil seluruh data yang dibutuhkan dashboard."""
    system_info = st.session_state.get("server_info") or {}
    
    catalog_list, total_items = fetch_catalog_data(
        page=page,
        per_page=PAGE_SIZE,
    )
    dashboard_metrics = fetch_dashboard_metrics() or {}

    return (
        system_info,
        catalog_list or [],
        max(0, int(total_items or 0)),
        dashboard_metrics,
    )


def main() -> None:
    """Entry point utama aplikasi Streamlit Yoru-Agent."""
    st.set_page_config(
        page_title=PAGE_TITLE,
        page_icon=PAGE_ICON,
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    
    render_styles()

    # Autentikasi sebelum menampilkan dashboard.
    if not require_login():
        st.stop()

    # Tombol logout.
    with st.sidebar:
        st.button(
            "Logout",
            use_container_width=True,
            on_click=logout,
        )

    st.title("🛡️ Yoru-Agent Dashboard")
    st.caption("Infrastructure Hardening Control Plane")
    st.divider()

    try:
        initialize_server_info()

        # Menjaga nomor halaman tetap valid ketika jumlah katalog berubah.
        page = max(1, int(st.session_state.get("page_num", 1)))

        system_info, catalog_list, total_items, dashboard_metrics = (
            _load_dashboard_data(page)
        )
    except Exception as exc:
        st.error(f"Gagal memuat data dashboard: {exc}")
        st.info(
            "Pastikan backend API aktif, konfigurasi koneksi benar, "
            "dan database lokal dapat diakses."
        )
        return

    render_metrics_row(system_info, dashboard_metrics)
    st.divider()

    render_control_bar()
    st.divider()

    render_catalog_table(catalog_list, total_items)


if __name__ == "__main__":
    main()