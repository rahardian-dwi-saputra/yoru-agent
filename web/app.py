from __future__ import annotations
import streamlit as st

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


PAGE_TITLE = "Yoru-Agent Security Dashboard"
PAGE_ICON = "🛡️"
PAGE_SIZE = 10


def initialize_server_info():
    """Mengambil informasi server sekali setiap sesi Streamlit."""

    if "server_info" not in st.session_state:
        server_info = fetch_system_info()

        st.session_state.server_info = server_info

        if server_info:
            save_server_info(server_info)

    return st.session_state.server_info


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