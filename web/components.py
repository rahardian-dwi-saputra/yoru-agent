import math
import streamlit as st
from services import (
  refresh_catalog_data, 
  trigger_audit_all, 
  trigger_single_audit,
  init_hardening_all,
  init_single_hardening,
  confirm_hardening_plan
)


def render_styles():
    """Memuat kustomisasi CSS tema Grafana."""
    st.markdown(
        """
        <style>
            .stApp {
                background-color: #111217;
                color: #d8d9db;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
            }
            .grafana-panel {
                background-color: #1e1f2b;
                border: 1px solid #2d2f3d;
                border-radius: 4px;
                padding: 16px;
                margin-bottom: 16px;
                box-shadow: 0 4px 6px rgba(0, 0, 0, 0.3);
            }
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
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
        </style>
    """,
        unsafe_allow_html=True,
    )

def render_metrics_row(sys_info, metrics_data):
    """Baris pertama: Kotak Informasi Sistem & Total Rules."""

    audit_ratio = metrics_data.get("audit_ratio", "0 / 0")
    hardening_ratio = metrics_data.get("hardening_ratio", "0 / 0")
    rollback_ratio = metrics_data.get("rollback_ratio", "0 / 0")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.markdown(
            f"""
            <div class="grafana-panel">
                <div class="metric-title">Informasi Sistem Operasi</div>
                <div class="metric-value">{sys_info.get('os_platform', '')}</div>
                <div style="font-size: 11px; color: #8e8f99; margin-top: 4px;">Arch: {sys_info.get('architecture', 'x86_64')}</div>
            </div>
        """,
            unsafe_allow_html=True,
        )

    with col2:
        st.markdown(
            f"""
            <div class="grafana-panel">
                <div class="metric-title">Total Audit (Berhasil / Total)</div>
                <div class="metric-value">{audit_ratio} <span style="font-size:13px; color:#36a2eb;">(Compliant)</span></div>
                <div style="font-size: 11px; color: #8e8f99; margin-top: 4px;">Status: Berdasarkan Katalog</div>
            </div>
        """,
            unsafe_allow_html=True,
        )

    with col3:
        st.markdown(
            f"""
            <div class="grafana-panel">
                <div class="metric-title">Total Hardening (Berhasil / Total)</div>
                <div class="metric-value">{hardening_ratio} <span style="font-size:13px; color:#4bc0c0;">(Applied)</span></div>
                <div style="font-size: 11px; color: #8e8f99; margin-top: 4px;">Status: Standar CIS Benchmark</div>
            </div>
        """,
            unsafe_allow_html=True,
        )

    with col4:
        st.markdown(
            f"""
            <div class="grafana-panel">
                <div class="metric-title">Total Rollback (Berhasil / Total)</div>
                <div class="metric-value">{rollback_ratio} <span style="font-size:13px; color:#ff6384;">(Restored)</span></div>
                <div style="font-size: 11px; color: #8e8f99; margin-top: 4px;">Status: Pemulihan Sistem</div>
            </div>
        """,
            unsafe_allow_html=True,
        )


@st.dialog("⚠️ Konfirmasi Hardening All")
def show_hardening_confirmation_modal(plan_data):
    message = plan_data.get("message", "Apakah Anda yakin ingin menjalankan aksi hardening?")
    plans_list = plan_data.get("plans", [])
    
    plan_id = plans_list[0].get("plan_id") if plans_list else None
    expires_at = plans_list[0].get("expires_at") if plans_list else "-"
    catalogs_affected = plans_list[0].get("catalogs", [])

    st.markdown(f"**Pesan Sistem:**\n> {message}")
    st.markdown(f"- **Plan ID:** `{plan_id}`")
    st.markdown(f"- **Total Katalog Terdampak:** `{len(catalogs_affected)} rules`")
    st.markdown(f"- **Kedaluwarsa:** `{expires_at}`")
    
    st.markdown("---")
    st.warning("Aksi ini akan mengubah konfigurasi sistem server. Lanjutkan?")

    col_yes, col_no = st.columns(2)
    
    with col_yes:
      if st.button("✅ Iya, Lanjutkan", use_container_width=True, type="primary"):
        if plan_id:
          success, response = confirm_hardening_plan(plan_id, approved=True)
          if success:
            st.success(response.get("message", "Hardening selesai diproses."))
            st.rerun()
          else:
            st.error(response.get("message", "Gagal mengeksekusi hardening."))
        else:
          st.error("Plan ID tidak ditemukan.")

    with col_no:
      if st.button("❌ Tidak, Batalkan", use_container_width=True):
        if plan_id:
          success, response = confirm_hardening_plan(plan_id, approved=False)

          if success and response.get("status") == "REJECTED":
            msg = response.get("message", "Hardening ALL dibatalkan.")
            st.warning(msg)
          else:
            st.warning("Hardening ALL dibatalkan.")
        else:
          st.warning("Hardening ALL dibatalkan.")
           
        st.rerun()


@st.dialog("⚠️ Konfirmasi Single Hardening")
def show_single_hardening_modal(rule_id, plan_data):
  message = plan_data.get(
    "message",
    f"Apakah Anda yakin ingin melakukan hardening untuk rule {rule_id}?",
  )
  plans_list = plan_data.get("plans", [])

  plan_id = plans_list[0].get("plan_id") if plans_list else None
  expires_at = plans_list[0].get("expires_at") if plans_list else "-"

  st.markdown(f"**Rule ID:** `{rule_id}`")
  st.markdown(f"**Pesan Sistem:**\n> {message}")
  st.markdown(f"- **Plan ID:** `{plan_id}`")
  st.markdown(f"- **Kedaluwarsa:** `{expires_at}`")

  st.markdown("---")
  st.warning("Aksi ini akan mengubah konfigurasi spesifik pada server. Lanjutkan?")

  col_yes, col_no = st.columns(2)

  with col_yes:
    if st.button(
      "✅ Iya, Lanjutkan",
      key=f"conf_yes_{rule_id}",
      use_container_width=True,
      type="primary",
    ):
      if plan_id:
        
        success, response = confirm_hardening_plan(
          plan_id=plan_id, 
          approved=True, 
          catalog=rule_id
        )

        if success:
          st.success(
            response.get(
              "message", f"Hardening rule {rule_id} selesai diproses."
            )
          )
          st.rerun()
        else:
          st.error(response.get("message", "Gagal mengeksekusi hardening."))
      else:
        st.error("Plan ID tidak ditemukan.")

  with col_no:
    if st.button(
      "❌ Tidak, Batalkan", key=f"conf_no_{rule_id}", use_container_width=True
    ):
      if plan_id:
       
        success, response = confirm_hardening_plan(
          plan_id=plan_id, 
          approved=False, 
          catalog=rule_id
        )

        if success and response.get("status") == "REJECTED":
          st.warning(
            response.get(
              "message", "Permintaan hardening ditolak oleh user."
            )
          )
        else:
          st.warning("Hardening dibatalkan.")
      else:
        st.warning("Hardening dibatalkan.")
      st.rerun()


def render_control_bar():
    """Baris kedua: Tombol Refresh & Aksi Global."""
    c_left, c_right = st.columns([1, 2])
    
    with c_left:
      if st.button("🔄 Refresh Katalog", use_container_width=True):
        st.cache_data.clear()

        success = refresh_catalog_data()

        if success:
          st.success("Data katalog berhasil diperbarui")
        else:
          st.warning("Gagal memperbarui dari API (menggunakan data lokal)")
            
        st.rerun()

    with c_right:
        btn_col1, btn_col2, btn_col3 = st.columns(3)

        with btn_col1:
          if st.button("🚀 Audit All", use_container_width=True, type="primary"):
            with st.spinner("Menjalankan seluruh prosedur Audit pada server..."):
              success, message = trigger_audit_all()

              if success:
                st.success(f"Audit All Berhasil! {message}")
                st.rerun()
              else:
                st.error(f"Gagal menjalankan Audit All: {message}")

        with btn_col2:
          if st.button("🔒 Hardening All", use_container_width=True):
            with st.spinner("Membuat plan hardening (/init)..."):
              success, response = init_hardening_all()

              if success and response.get("status") == "PENDING_APPROVAL":
                show_hardening_confirmation_modal(response)
              else:
                st.error(response.get("message", "Gagal menginisialisasi plan hardening."))

        with btn_col3:
            if st.button("🔄 Rollback All", use_container_width=True):
                st.toast("Mengembalikan konfigurasi sistem (Rollback)...", icon="🔄")

    st.markdown("<br>", unsafe_allow_html=True)


def render_catalog_table(catalog_list, total_items):
  """Merender tabel katalog interaktif dengan pagination, tata letak kolom kustom,

  dan tombol aksi bersyarat (Audit, Hardening, Rollback, Detail) berdasarkan nilai audit_only.
  """
  st.markdown("#### 📋 Katalog Rules Keamanan Sistem & Aksi Eksekusi")

  items_per_page = 10
  total_pages = math.ceil(total_items / items_per_page) if total_items > 0 else 1

  if "page_num" not in st.session_state:
    st.session_state.page_num = 1

  # Navigasi Pagination di Bagian Atas
  nav_col1, _, nav_col3 = st.columns([2, 6, 2])
  with nav_col1:
    current_page = st.number_input(
        "Halaman",
        min_value=1,
        max_value=max(1, total_pages),
        value=st.session_state.page_num,
        step=1,
        key="page_input_num",
    )
    if current_page != st.session_state.page_num:
      st.session_state.page_num = current_page
      st.rerun()

  with nav_col3:
    st.markdown(
        f"<div style='text-align: right; padding-top: 28px; color: #8e8f99;"
        f" font-size: 13px;'>Total: {total_items} rules</div>",
        unsafe_allow_html=True,
    )

  st.markdown("---")

  if not catalog_list:
    st.info(
      "Belum ada data katalog. Pastikan backend API aktif atau lakukan sinkronisasi."
    )
    return

  # Render Header Tabel Kustom (Agar selaras dengan kolom data di bawahnya)
  header_cols = st.columns([1, 1.2, 3, 1.2, 1.2, 2.5])
  with header_cols[0]:
    st.markdown("**ID**")
  with header_cols[1]:
    st.markdown("**Kode CIS**")
  with header_cols[2]:
    st.markdown("**Judul & Nama Rule**")
  with header_cols[3]:
    st.markdown("**Kategori**")
  with header_cols[4]:
    st.markdown("**Status Audit**")
  with header_cols[5]:
    st.markdown("**Aksi**")

  st.markdown("---")

  # Render Baris Data Katalog Secara Interaktif
  for idx, item in enumerate(catalog_list):
    rule_id = item.get("id")
    kode_cis = item.get("kode_cis")
    cis_judul = item.get("cis_judul", "-")
    nama_rule = item.get("nama", "-")
    kategori = item.get("kategori", "-")
    status_audit = item.get("status_audit", "Pending")
    audit_only = bool(item.get("audit_only", False))

    row_cols = st.columns([1, 1.2, 3, 1.2, 1.2, 2.5])

    # Kolom 1: ID
    with row_cols[0]:
      st.markdown(
        f"<p style='padding-top: 10px;'>{rule_id}</p>", 
        unsafe_allow_html=True
      )

    # Kolom 2: Kode CIS
    with row_cols[1]:
      st.markdown(
        f"<p style='padding-top: 10px;'>{kode_cis}</p>", 
        unsafe_allow_html=True
      )

    # Kolom 3: CIS Judul dan Nama Rule
    with row_cols[2]:
      st.markdown(
        f"<div style='font-size: 13px; font-weight: 600; color: #f7f8f9;'>{cis_judul}</div>"
        f"<div style='font-size: 12px; color: #8e8f99; margin-top: 2px;'>{nama_rule}</div>",
        unsafe_allow_html=True,
      )

    # Kolom 4: Kategori
    with row_cols[3]:
      st.markdown(
        f"<p style='padding-top: 10px;'>{kategori}</p>", 
        unsafe_allow_html=True
      )

    # Kolom 5: Status Audit dalam bentuk label (Badge warna dinamis)
    with row_cols[4]:
      color_map = {
        "COMPLIANT": "#28a745",
        "NON_COMPLIANT": "#ffc107",
        "PENDING": "#ffc107",
        "SKIPPED": "#17a2b8",
        "FAILED": "#dc3545",
      }
      badge_color = color_map.get(status_audit.upper(), "#6c757d")
      st.markdown(
        f"<div style='padding-top: 8px;'><span style='background-color: {badge_color}; color: white; padding: 3px 8px; border-radius: 4px; font-size: 11px; font-weight: 600;'>{status_audit}</span></div>",
        unsafe_allow_html=True,
      )

    # Kolom 6: Tombol Aksi (Audit, Hardening, Rollback, Detail / Audit & Detail jika audit_only)
    with row_cols[5]:
      if audit_only:
        # Jika audit_only = true, tampilkan 2 tombol saja
        b_col1, b_col2 = st.columns(2)
        with b_col1:
          if st.button("🔍 Audit", key=f"audit_{rule_id}_{idx}", use_container_width=True):
            with st.spinner(f"Menjalankan Audit {rule_id}..."):
              success, message = trigger_single_audit(rule_id)
              if success:
                st.success(f"Berhasil: {message}")
                st.rerun()
              else:
                st.error(f"Gagal: {message}")
        with b_col2:
          if st.button("📄 Detail", key=f"detail_{rule_id}_{idx}", use_container_width=True):
            st.toast(f"Melihat detail untuk {rule_id}...", icon="📋")
            # Tambahkan logika modal/ekspansi detail di sini
      else:
        # Jika audit_only = false, tampilkan 4 tombol lengkap
        b_col1, b_col2, b_col3, b_col4 = st.columns(4)
        with b_col1:
          if st.button("🔍", key=f"audit_{rule_id}_{idx}", use_container_width=True, help="Audit"):
            with st.spinner(f"Menjalankan Audit {rule_id}..."):
              success, message = trigger_single_audit(rule_id)
              if success:
                st.success(f"Berhasil: {message}")
                st.rerun()
              else:
                st.error(f"Gagal: {message}")

        with b_col2:
          if st.button("🔒", key=f"hard_{rule_id}_{idx}", use_container_width=True, help="Hardening"):
            with st.spinner(f"Membuat plan hardening untuk {rule_id}..."):
              success, response = init_single_hardening(rule_id)
              if success and response.get("status") == "PENDING_APPROVAL":
                show_single_hardening_modal(rule_id, response)
              else:
                st.error(response.get("message", "Gagal menginisialisasi plan hardening."))

        with b_col3:
          if st.button("🔄", key=f"roll_{rule_id}_{idx}", use_container_width=True, help="Rollback"):
            st.toast(f"Rollback {rule_id}", icon="🔄")
        with b_col4:
          if st.button("📄", key=f"det_{rule_id}_{idx}", use_container_width=True, help="Detail"):
            st.toast(f"Detail {rule_id}", icon="📋")

    st.markdown("<hr style='margin: 4px 0px; border-color: #2d2f3d;'>", unsafe_allow_html=True)

  # Indikator Halaman di Bawah
  st.markdown(
    f"<p style='text-align: center; color: #8e8f99; font-size: 12px; margin-top: 15px;'>Halaman {st.session_state.page_num} dari {total_pages}</p>",
    unsafe_allow_html=True,
  )