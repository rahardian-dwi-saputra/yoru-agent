import streamlit as st
from components import (
    render_catalog_table,
    render_control_bar,
    render_metrics_row,
    render_styles,
)
from services import fetch_catalog_data, fetch_system_info, fetch_dashboard_metrics

# 1. Konfigurasi Halaman
st.set_page_config(
    page_title="Yoru-Agent Security Dashboard",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# 2. Muat Kustomisasi Tema Grafana
render_styles()

# 3. Header Dashboard
st.markdown("### 🛡️ Yoru-Agent Dashboard — Infrastructure Hardening Control Plane")
st.markdown("---")

# 4. Ambil Data (Cached via Services)
sys_info = fetch_system_info()
catalog_list = fetch_catalog_data()
dashboard_metrics = fetch_dashboard_metrics()

# 5. Render Baris 1: Informasi Sistem & Metrics
render_metrics_row(sys_info, dashboard_metrics)

# 6. Render Baris 2: Tombol Kontrol & Aksi
render_control_bar()

# 7. Render Baris 3: Tabel Katalog dengan Pagination
render_catalog_table(catalog_list)