import math
import requests
import streamlit as st


st.set_page_config(
    page_title="Yoru-Agent Security Dashboard",
    page_icon="🛡️",
    layout="wide",
    initial_sidebar_state="collapsed",
)


st.markdown(
    """
    <style>
        /* Global Background & Font */
        .stApp {
            background-color: #111217;
            color: #d8d9db;
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        }
        
        /* Grafana Panel Box */
        .grafana-panel {
            background-color: #1e1f2b;
            border: 1px solid #2d2f3d;
            border-radius: 4px;
            padding: 16px;
            margin-bottom: 16px;
            box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
        }
        
        /* Metric Typography */
        .metric-title {
            font-size: 12px;
            color: #8e8f99;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 4px;
        }
        .metric-value {
            font-size: 20px;
            font-weight: 600;
            color: #f7f8f9;
        }
        
        /* Table Styling */
        dataframe, th, td {
            background-color: #1e1f2b !important;
            color: #d8d9db !important;
        }
        
        /* Hide Streamlit Header Elements */
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
    </style>
""",
    unsafe_allow_html=True,
)

# ==========================================
# KONFIGURASI API BACKEND
# ==========================================
API_BASE_URL = "http://localhost:8000/api/v1"  # Sesuaikan port jika berbeda


# Fungsi pembantu untuk mengambil data dari FastAPI
@st.cache_data(ttl=5)
def fetch_system_info():
    try:
        response = requests.get(f"{API_BASE_URL}/system/info", timeout=3)
        if response.status_code == 200:
            return response.json()
    except Exception:
        pass
    return {
        "os": "Ubuntu 24.04 LTS (Mock)",
        "hostname": "yoru-node-01",
        "kernel": "5.15.0-generic",
    }


# Mock data katalog rules (bisa diganti dengan endpoint API katalog Anda jika sudah ada)
@st.cache_data
def get_catalog_data():
    # Contoh 25 data katalog untuk demonstrasi pagination (10 data per halaman)
    data = []
    for i in range(1, 26):
        cat_type = "Audit" if i % 2 == 0 else "Hardening"
        data.append(
            {
                "id": f"K{i:02d}",
                "nama": f"Rule Keamanan Sistem #{i}",
                "kode_cis": f"CIS 3.{i}.{i}",
                "kategori": "Access Control" if i % 3 == 0 else "Kernel Hardening",
                "action": cat_type,
            }
        )
    return data


# ==========================================
# HEADER DASHBOARD
# ==========================================
st.markdown(
    "### 🛡️ Yoru-Agent Dashboard — Infrastructure Hardening Control Plane"
)
st.markdown("---")

# ==========================================
# BARIS PERTAMA: 3 KOTAK INFORMASI (METRICS)
# ==========================================
sys_info = fetch_system_info()
catalog_list = get_catalog_data()

# Menghitung Total Rules Audit & Hardening
total_audit = sum(1 for x in catalog_list if x["action"] == "Audit")
total_hardening = sum(1 for x in catalog_list if x["action"] == "Hardening")

col1, col2, col3 = st.columns(3)

with col1:
    st.markdown(
        f"""
        <div class="grafana-panel">
            <div class="metric-title">Informasi Sistem Operasi</div>
            <div class="metric-value">{sys_info.get('os', 'Ubuntu 24.04')}</div>
            <div style="font-size: 11px; color: #8e8f99; margin-top: 4px;">Host: {sys_info.get('hostname', 'localhost')}</div>
        </div>
    """,
        unsafe_allow_html=True,
    )

with col2:
    st.markdown(
        f"""
        <div class="grafana-panel">
            <div class="metric-title">Jumlah Rules Audit</div>
            <div class="metric-value">{total_audit} <span style="font-size:13px; color:#36a2eb;">(Aktif)</span></div>
            <div style="font-size: 11px; color: #8e8f99; margin-top: 4px;">Status: Siap Dieksekusi</div>
        </div>
    """,
        unsafe_allow_html=True,
    )

with col3:
    st.markdown(
        f"""
        <div class="grafana-panel">
            <div class="metric-title">Jumlah Rules Hardening</div>
            <div class="metric-value">{total_hardening} <span style="font-size:13px; color:#4bc0c0;">(Aktif)</span></div>
            <div style="font-size: 11px; color: #8e8f99; margin-top: 4px;">Status: Standar CIS Benchmark</div>
        </div>
    """,
        unsafe_allow_html=True,
    )

# ==========================================
# BARIS KEDUA: TOMBOL KONTROL & AKSI
# ==========================================
c_left, c_right = st.columns([1, 2])

with c_left:
    if st.button("🔄 Refresh Katalog", use_container_width=True):
        st.cache_data.clear()
        st.success("Katalog berhasil direfresh!")
        st.rerun()

with c_right:
    btn_col1, btn_col2, btn_col3 = st.columns(3)
    with btn_col1:
        if st.button("🚀 Audit All", use_container_width=True, type="primary"):
            st.toast("Menjalankan seluruh prosedur Audit...", icon="ℹ️")
            # Tambahkan logika request ke API /api/v1/audit/all di sini
    with btn_col2:
        if st.button("🔒 Hardening All", use_container_width=True):
            st.toast(
                "Menerapkan seluruh konfigurasi Hardening...", icon="⚠️"
            )
            # Tambahkan logika request ke API /api/v1/hardening/all di sini
    with btn_col3:
        if st.button("rollback Rollback All", use_container_width=True):
            st.toast(
                "Mengembalikan konfigurasi sistem (Rollback)...", icon="🔄"
            )
            # Tambahkan logika request ke API /api/v1/rollback/all di sini

st.markdown("<br>", unsafe_allow_html=True)

# ==========================================
# BARIS KETIGA: TABEL KATALOG DENGAN PAGINATION
# ==========================================
st.markdown("#### 📋 Katalog Rules Keamanan Sistem")

# Pengaturan Pagination (10 data per halaman)
items_per_page = 10
total_items = len(catalog_list)
total_pages = math.ceil(total_items / items_per_page)

# State untuk halaman aktif
if "page_num" not in st.session_state:
    st.session_state.page_num = 1

# Kontrol navigasi halaman di atas tabel
nav_col1, nav_col2, nav_col3 = st.columns([2, 6, 2])
with nav_col1:
    current_page = st.number_input(
        "Halaman",
        min_value=1,
        max_value=max(1, total_pages),
        value=st.session_state.page_num,
        step=1,
    )
    st.session_state.page_num = current_page

with nav_col3:
    st.markdown(
        f"<div style='text-align: right; padding-top: 28px; color: #8e8f99; font-size: 13px;'>Menampilkan dari {total_items} total rules</div>",
        unsafe_allow_html=True,
    )

# Hitung potongan data untuk halaman aktif
start_idx = (st.session_state.page_num - 1) * items_per_page
end_idx = start_idx + items_per_page
current_data_slice = catalog_list[start_idx:end_idx]

# Format tampilan tabel agar sesuai kolom yang diminta:
# (ID Katalog, Nama Katalog, Kode CIS, Kategori, Action)
formatted_table_data = []
for item in current_data_slice:
    formatted_table_data.append(
        {
            "ID Katalog": item["id"],
            "Nama Katalog": item["nama"],
            "Kode CIS": item["kode_cis"],
            "Kategori": item["kategori"],
            "Action": item["action"],
        }
    )

# Render tabel menggunakan Streamlit dataframe dengan kustomisasi kolom
st.dataframe(
    formatted_table_data,
    use_container_width=True,
    hide_index=True,
    column_config={
        "ID Katalog": st.column_config.TextColumn(
            "ID Katalog", width="small"
        ),
        "Nama Katalog": st.column_config.TextColumn(
            "Nama Katalog", width="large"
        ),
        "Kode CIS": st.column_config.TextColumn("Kode CIS", width="medium"),
        "Kategori": st.column_config.TextColumn("Kategori", width="medium"),
        "Action": st.column_config.TextColumn("Action", width="small"),
    },
)

# Indikator halaman di bagian bawah tabel
st.markdown(
    f"<p style='text-align: center; color: #8e8f99; font-size: 12px;'>Halaman {st.session_state.page_num} dari {total_pages}</p>",
    unsafe_allow_html=True,
)