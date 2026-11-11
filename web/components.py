from __future__ import annotations

import html
import math
from datetime import datetime
from pathlib import Path
from typing import Any

import streamlit as st

from database import get_catalog_detail
from services import (
    confirm_hardening_plan,
    confirm_rollback_plan,
    init_hardening_all,
    init_rollback_all,
    init_single_hardening,
    init_single_rollback,
    refresh_catalog_data,
    trigger_audit_all,
    trigger_single_audit,
    fetch_catalog_ai_advice,
    fetch_global_log_summary
)
from utils_pdf import generate_pentest_pdf
from config.web import WEB_STORAGE_DIR


ITEMS_PER_PAGE = 10

PDF_FILENAME = (
    WEB_STORAGE_DIR / "reports" / "Yoru_Agent_Server_Security_Assessment_Report.pdf"
)


def _safe(value: Any, default: str = "-") -> str:
    """Mengubah nilai menjadi teks aman untuk ditampilkan pada HTML."""
    if value is None or str(value).strip() == "":
        return default
    return html.escape(str(value))


def _as_bool(value: Any) -> bool:
    """Normalisasi boolean dari SQLite/API, termasuk nilai string '0'."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value != 0
    return str(value).strip().lower() in {"1", "true", "yes", "y", "ya", "on"}


def _catalog_value(item: dict, *keys: str, default: Any = "-") -> Any:
    """Mengambil field dengan dukungan nama lama dan nama alternatif."""
    for key in keys:
        value = item.get(key)
        if value not in (None, ""):
            return value
    return default


def _format_timestamp(value: Any) -> str:
    if not value or str(value).strip().lower() in {"-", "none"}:
        return "-"
    text = str(value)
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text.split(".")[0], fmt).strftime(
                "%d-%m-%Y %H:%M:%S"
            )
        except ValueError:
            continue
    return text

def _render_flash_message() -> None:
    """Menampilkan flash message dari session state jika ada."""
    flash = st.session_state.pop("flash_message", None)
    if flash:
        msg_type = flash.get("type")
        text = flash.get("text")
        if msg_type == "success":
            st.success(text)
        elif msg_type == "warning":
            st.warning(text)
        elif msg_type == "error":
            st.error(text)
        else:
            st.info(text)


def render_styles() -> None:
    """Memuat tema gelap bergaya Grafana."""
    st.markdown(
        """
        <style>
            .stApp {
                background-color: #111217;
                color: #d8d9db;
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
                    Roboto, Helvetica, Arial, sans-serif;
            }
            .grafana-panel {
                background: #1e1f2b;
                border: 1px solid #2d2f3d;
                border-radius: 6px;
                padding: 16px;
                margin-bottom: 12px;
            }
            .metric-title {
                color: #8e8f99;
                font-size: 12px;
                letter-spacing: .4px;
                text-transform: uppercase;
                margin-bottom: 5px;
            }
            .metric-value {
                color: #f7f8f9;
                font-size: 20px;
                font-weight: 600;
            }
            #MainMenu, footer { visibility: hidden; }
        </style>
        """,
        unsafe_allow_html=True,
    )


def render_metrics_row(sys_info: dict, metrics_data: dict) -> None:
    """Menampilkan informasi sistem dan ringkasan status katalog."""
    sys_info = sys_info or {}
    metrics_data = metrics_data or {}

    metrics = [
        (
            "Informasi Sistem Operasi",
            _catalog_value(sys_info, "os_platform", default="Tidak diketahui"),
            (
                f"Hostname: {_safe(sys_info.get('hostname'), 'Tidak diketahui')} "
                f"| Arch: {_safe(sys_info.get('architecture'), 'Tidak diketahui')}"
            ),
            "#f7f8f9",
        ),
        (
            "Total Audit (Berhasil / Total)",
            metrics_data.get("audit_ratio", "0 / 0"),
            "Status: Berdasarkan katalog",
            "#36a2eb",
        ),
        (
            "Total Hardening (Berhasil / Total)",
            metrics_data.get("hardening_ratio", "0 / 0"),
            "Status: Standar CIS Benchmark",
            "#4bc0c0",
        ),
        (
            "Total Rollback (Berhasil / Total)",
            metrics_data.get("rollback_ratio", "0 / 0"),
            "Status: Pemulihan sistem",
            "#ff6384",
        ),
    ]

    columns = st.columns(4)
    for column, (title, value, caption, accent) in zip(columns, metrics):
        with column:
            st.markdown(
                f"""
                <div class="grafana-panel">
                    <div class="metric-title">{_safe(title)}</div>
                    <div class="metric-value" style="color:{accent}">
                        {_safe(value)}
                    </div>
                    <div style="font-size:11px;color:#8e8f99;margin-top:5px">
                        {_safe(caption)}
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )


def _get_plan_details(plan_data: dict) -> tuple[str | None, str, list]:
    plans = plan_data.get("plans") or []
    plan = plans[0] if plans and isinstance(plans[0], dict) else {}
    return (
        plan.get("plan_id"),
        _format_timestamp(plan.get("expires_at")),
        plan.get("catalogs") or [],
    )


@st.dialog("⚠️ Konfirmasi Aksi")
def _show_action_confirmation(
    action: str,
    scope: str,
    plan_data: dict,
    rule_id: str | None = None,
) -> None:
    """Dialog konfirmasi tunggal untuk hardening dan rollback."""
    confirm_fn = (
        confirm_hardening_plan if action == "hardening" else confirm_rollback_plan
    )
    action_label = "Hardening" if action == "hardening" else "Rollback"
    is_all = scope == "all"
    plan_id, expires_at, affected_catalogs = _get_plan_details(plan_data)

    if rule_id:
      detail = get_catalog_detail(rule_id)

      message_key = (
        "pesan_hardening"
        if action == "hardening"
        else "pesan_rollback"
      )

      message = detail.get(message_key) if detail else None

    elif is_all:
      message = (
        "Anda akan menjalankan proses Hardening All terhadap seluruh "
        "katalog yang mendukung mekanisme hardening.\n\n"
        "Sistem akan menerapkan konfigurasi keamanan pada server "
        "berdasarkan rekomendasi CIS Ubuntu Linux 24.04 LTS Benchmark "
        "v2.0.0 dan pemetaan kontrol terhadap Undang-Undang Nomor "
        "27 Tahun 2022 tentang Pelindungan Data Pribadi (UU PDP).\n\n"
        "Proses ini mencakup penguatan keamanan akses SSH, pengaturan "
        "hak akses dan penyimpanan log sistem, serta pengamanan "
        "konfigurasi jaringan dan kernel.\n\n"
        "Katalog yang hanya memiliki mode Audit Only tidak akan "
        "mengalami perubahan konfigurasi.\n\n"
        "Pastikan Anda telah memahami dampak perubahan konfigurasi "
        "sebelum melanjutkan."
        if action == "hardening"
        else
        "Anda akan menjalankan proses Rollback All terhadap seluruh "
        "katalog yang mendukung mekanisme rollback.\n\n"
        "Sistem akan mengembalikan konfigurasi keamanan server ke "
        "kondisi sebelumnya berdasarkan data backup yang tersimpan "
        "ketika proses hardening dilakukan.\n\n"
        "Proses ini dapat mencakup pemulihan konfigurasi SSH, "
        "pengaturan hak akses dan penyimpanan log Journald, serta "
        "konfigurasi keamanan jaringan dan kernel.\n\n"
        "Katalog yang hanya memiliki mode Audit Only tidak akan "
        "mengalami perubahan konfigurasi.\n\n"
        "Perhatian: Rollback dapat mengembalikan konfigurasi ke "
        "kondisi yang memiliki tingkat keamanan lebih rendah. "
        "Pastikan tindakan ini memang diperlukan sebelum melanjutkan."
      )

    else:
      message = None

    message = message or plan_data.get(
      "message",
      f"Apakah Anda yakin ingin menjalankan {action_label.lower()}?",
    )

    if rule_id:
        st.markdown(f"**Rule ID:** `{_safe(rule_id)}`")

    formatted_message = message.replace("\n", "  \n")

    st.markdown(f"**Pesan sistem:**\n\n{formatted_message}")
    st.markdown(f"- **Plan ID:** `{_safe(plan_id)}`")
    if is_all:
        st.markdown(f"- **Total katalog terdampak:** {len(affected_catalogs)} rules")
    st.markdown(f"- **Kedaluwarsa:** `{_safe(expires_at)}`")
    st.divider()

    warning = (
        "Aksi ini akan mengubah konfigurasi sistem server."
        if action == "hardening"
        else "Aksi ini akan mengembalikan konfigurasi sistem ke kondisi sebelumnya."
    )
    st.warning(f"{warning} Lanjutkan?")

    yes_col, no_col = st.columns(2)

    with yes_col:
        if st.button(
            "✅ Iya, Lanjutkan",
            key=f"{action}_{scope}_{rule_id or 'all'}_approve",
            type="primary",
            use_container_width=True,
        ):
            if not plan_id:
                st.session_state["flash_message"] = {
                    "type": "error",
                    "text": "Plan ID tidak ditemukan."
                }
                st.rerun()

            with st.spinner(f"Menjalankan {action_label.lower()}..."):
                success, response = confirm_fn(
                    plan_id=plan_id,
                    approved=True,
                    **({"catalog": rule_id} if rule_id else {}),
                )
            
            msg = response.get("message") if isinstance(response, dict) else str(response)
            if success:
                st.session_state["flash_message"] = {
                    "type": "success",
                    "text": msg or f"{action_label} berhasil diproses."
                }
            else:
                st.session_state["flash_message"] = {
                    "type": "error",
                    "text": msg or f"Gagal menjalankan {action_label.lower()}."
                }
            st.rerun()

    with no_col:
        if st.button(
            "❌ Tidak, Batalkan",
            key=f"{action}_{scope}_{rule_id or 'all'}_reject",
            use_container_width=True,
        ):
            if plan_id:
                with st.spinner("Membatalkan plan..."):
                    success, response = confirm_fn(
                        plan_id=plan_id,
                        approved=False,
                        **({"catalog": rule_id} if rule_id else {}),
                    )
                msg = response.get("message") if isinstance(response, dict) else str(response)
                if success and msg:
                    st.session_state["flash_message"] = {
                        "type": "warning",
                        "text": msg
                    }
                else:
                    st.session_state["flash_message"] = {
                        "type": "warning",
                        "text": f"{action_label} dibatalkan."
                    }
            else:
                st.session_state["flash_message"] = {
                    "type": "warning",
                    "text": f"{action_label} dibatalkan."
                }
            st.rerun()


# Nama fungsi berikut dipertahankan agar kompatibel dengan pemanggil sebelumnya.
def show_hardening_confirmation_modal(plan_data: dict) -> None:
    _show_action_confirmation("hardening", "all", plan_data)


def show_single_hardening_modal(rule_id: str, plan_data: dict) -> None:
    _show_action_confirmation("hardening", "single", plan_data, rule_id)


def show_rollback_all_confirmation_modal(plan_data: dict) -> None:
    _show_action_confirmation("rollback", "all", plan_data)


def show_single_rollback_modal(rule_id: str, plan_data: dict) -> None:
    _show_action_confirmation("rollback", "single", plan_data, rule_id)


@st.dialog("✨ AI Global Executive Summary")
def show_ai_summary_modal() -> None:
    """Dialog untuk menampilkan ringkasan eksekutif global dari AI."""
    with st.spinner("Menganalisis seluruh log server dengan AI..."):
        success, response, error = fetch_global_log_summary()

    if not success:
        st.session_state["flash_message"] = {
            "type": "error",
            "text": error or "Gagal memuat AI Summary."
        }
        st.rerun()

    summary_text = response.get("executive_summary", "Tidak ada ringkasan yang dihasilkan.")
    total_analyzed = response.get("total_catalogs_analyzed", 0)

    st.markdown(f"**Total Katalog Dianalisis:** `{total_analyzed}` rules")
    st.divider()
    st.markdown(summary_text)
    st.divider()

    if st.button("Tutup", use_container_width=True):
        st.rerun()


@st.dialog("🤖 AI Security Advisor")
def show_ai_advisor_modal(rule_id: str) -> None:
    """Dialog untuk menampilkan saran keamanan AI pada katalog spesifik."""
    detail = get_catalog_detail(rule_id)
    rule_name = detail.get("nama") if detail else rule_id

    with st.spinner(f"Meminta analisis AI untuk rule {rule_id}..."):
        success, response, error = fetch_catalog_ai_advice(rule_id)

    if not success:
        st.session_state["flash_message"] = {
            "type": "error",
            "text": error or f"Gagal mendapatkan AI advice untuk katalog {rule_id}."
        }
        st.rerun()

    ai_advice = response.get("ai_advice", {})
    summary = ai_advice.get("summary", "-")
    root_cause = ai_advice.get("root_cause", "-")
    recommendation = ai_advice.get("recommendation", "-")

    st.markdown(f"### Rule: `{_safe(rule_id)}`")
    st.markdown(f"**Nama Kontrol:** {_safe(rule_name)}")
    st.divider()

    st.markdown("**📝 Ringkasan Analisis:**")
    st.info(summary)

    st.markdown("**🔍 Akar Masalah (Root Cause):**")
    st.warning(root_cause)

    st.markdown("**💡 Rekomendasi Mitigasi:**")
    st.success(recommendation)

    st.divider()
    if st.button("Tutup", use_container_width=True):
        st.rerun()


@st.dialog("📄 Detail Katalog Rule")
def show_catalog_detail_modal(rule_id: str) -> None:
    """Menampilkan metadata, deskripsi, dan riwayat eksekusi katalog."""
    detail = get_catalog_detail(rule_id)
    if not detail:
        st.error(f"Data untuk rule {rule_id} tidak ditemukan.")
        if st.button("Tutup", use_container_width=True):
            st.rerun()
        return

    st.markdown(f"### `{_safe(detail.get('id'))}` — {_safe(detail.get('nama'))}")
    st.divider()

    left, right = st.columns(2)
    with left:
        st.markdown(f"**Kode CIS:** `{_safe(detail.get('kode_cis'))}`")
        st.markdown(f"**Kategori:** {_safe(detail.get('kategori'))}")
        st.markdown(
            f"**Audit Only:** {'Iya' if _as_bool(detail.get('audit_only')) else 'Tidak'}"
        )
    with right:
        risiko = _catalog_value(detail, "risiko", "resiko")
        judul_cis = _catalog_value(detail, "judul_cis", "cis_judul")
        st.markdown(f"**Risiko:** {_safe(risiko)}")
        st.markdown(f"**Judul CIS:** {_safe(judul_cis)}")

    st.divider()
    st.markdown("**Deskripsi**")
    st.write(detail.get("deskripsi") or "-")

    st.markdown("**Status & Riwayat Eksekusi**")
    status_columns = st.columns(3)
    history = (
        ("Audit", "status_audit", "waktu_audit"),
        ("Hardening", "status_hardening", "waktu_hardening"),
        ("Rollback", "status_rollback", "waktu_rollback"),
    )
    for column, (label, status_key, time_key) in zip(status_columns, history):
        with column:
            st.markdown(f"**{label}**")
            st.code(str(detail.get(status_key) or "-"), language=None)
            st.caption(f"Waktu: {_format_timestamp(detail.get(time_key))}")

    if st.button("Tutup", use_container_width=True):
        st.rerun()


def _open_catalog_detail(rule_id: str) -> None:
    """Membuka halaman detail katalog yang dipilih."""
    st.session_state["selected_catalog_id"] = rule_id
    st.switch_page("pages/detail_katalog.py")


def _run_audit(rule_id: str | None = None) -> None:
    label = f"Audit {rule_id}" if rule_id else "Audit All"
    with st.spinner(f"Menjalankan {label}..."):
        success, message = (
            trigger_single_audit(rule_id) if rule_id else trigger_audit_all()
        )

    if success:
        st.success(message or f"{label} berhasil dijalankan.")
        st.rerun()
    st.error(message or f"Gagal menjalankan {label}.")


def _start_plan(action: str, rule_id: str | None = None) -> None:
    is_hardening = action == "hardening"
    action_label = "hardening" if is_hardening else "rollback"
    init_fn = (
        init_single_hardening if is_hardening and rule_id
        else init_hardening_all if is_hardening
        else init_single_rollback if rule_id
        else init_rollback_all
    )

    with st.spinner(f"Membuat plan {action_label}..."):
        success, response = init_fn(rule_id) if rule_id else init_fn()

    if not success or response.get("status") != "PENDING_APPROVAL":
        st.error(response.get("message", f"Gagal menginisialisasi plan {action_label}."))
        return

    if is_hardening:
        if rule_id:
            show_single_hardening_modal(rule_id, response)
        else:
            show_hardening_confirmation_modal(response)
    elif rule_id:
        show_single_rollback_modal(rule_id, response)
    else:
        show_rollback_all_confirmation_modal(response)


def render_control_bar() -> None:
    """Menampilkan tombol sinkronisasi dan aksi global."""
    refresh_col, action_col = st.columns([1, 2])

    with refresh_col:
        if st.button("🔄 Refresh Katalog", use_container_width=True):
            st.cache_data.clear()
            if refresh_catalog_data():
                st.success("Data katalog berhasil diperbarui.")
            else:
                st.warning("Gagal memperbarui dari API. Data lokal tetap digunakan.")
            st.rerun()

    with action_col:
        audit_col, hardening_col, rollback_col = st.columns(3)
        with audit_col:
            if st.button("🚀 Audit All", type="primary", use_container_width=True):
                _run_audit()
        with hardening_col:
            if st.button("🔒 Hardening All", use_container_width=True):
                _start_plan("hardening")
        with rollback_col:
            if st.button("🔄 Rollback All", use_container_width=True):
                _start_plan("rollback")


def _render_pdf_export() -> None:
    """Membuat laporan PDF dan menyediakan tombol unduh."""
    if st.button("📥 Export PDF Report", use_container_width=True):
        try:
            with st.spinner("Menyiapkan laporan PDF..."):
                pdf_path = Path(generate_pentest_pdf(output_filename=PDF_FILENAME))
                if not pdf_path.is_file():
                    raise FileNotFoundError("File PDF tidak ditemukan.")

                st.session_state["yoru_pdf_data"] = pdf_path.read_bytes()
            st.success("PDF siap diunduh.")
        except Exception as exc:
            st.error(f"Gagal membuat laporan PDF: {exc}")

    pdf_data = st.session_state.get("yoru_pdf_data")
    if pdf_data:
        st.download_button(
            "💾 Unduh File PDF",
            data=pdf_data,
            file_name=PDF_FILENAME,
            mime="application/pdf",
            key="download_pdf_report",
            use_container_width=True,
        )


def _render_status_badge(status: Any) -> None:
    status_text = str(status or "PENDING").upper()
    colors = {
        "COMPLIANT": "#28a745",
        "NON_COMPLIANT": "#ffc107",
        "PENDING": "#ffc107",
        "SKIPPED": "#17a2b8",
        "SUCCESS": "#28a745",
        "FAILED": "#dc3545",
        "ERROR": "#dc3545",
    }
    color = colors.get(status_text, "#6c757d")
    st.markdown(
        f"""
        <span style="
            background:{color};color:#fff;padding:3px 8px;
            border-radius:4px;font-size:11px;font-weight:600">
            {_safe(status_text)}
        </span>
        """,
        unsafe_allow_html=True,
    )


def _render_catalog_actions(item: dict, index: int) -> None:
    rule_id = str(item.get("id", ""))
    audit_only = _as_bool(item.get("audit_only"))

    if audit_only:
        audit_col, detail_col, ai_col = st.columns(3)
        with audit_col:
            if st.button(
                "🔍 Audit",
                key=f"audit_{rule_id}_{index}",
                use_container_width=True,
            ):
                _run_audit(rule_id)
        with detail_col:
            if st.button(
                "📄 Detail",
                key=f"detail_{rule_id}_{index}",
                use_container_width=True,
            ):
                _open_catalog_detail(rule_id)
        with ai_col:
            if st.button(
                "🤖 AI",
                key=f"ai_{rule_id}_{index}",
                help="AI Advisor",
                use_container_width=True,
            ):
                show_ai_advisor_modal(rule_id)
        return

    audit_col, hard_col, rollback_col, detail_col, ai_col = st.columns(5)
    with audit_col:
        if st.button("🔍", key=f"audit_{rule_id}_{index}", help="Audit", use_container_width=True):
            _run_audit(rule_id)
    with hard_col:
        if st.button("🔒", key=f"hard_{rule_id}_{index}", help="Hardening", use_container_width=True):
            _start_plan("hardening", rule_id)
    with rollback_col:
        if st.button("🔄", key=f"roll_{rule_id}_{index}", help="Rollback", use_container_width=True):
            _start_plan("rollback", rule_id)
    with detail_col:
        if st.button("📄", key=f"detail_{rule_id}_{index}", help="Detail", use_container_width=True):
            _open_catalog_detail(rule_id)
    with ai_col:
        if st.button("🤖", key=f"ai_{rule_id}_{index}", help="AI Advisor", use_container_width=True):
            show_ai_advisor_modal(rule_id)


def render_catalog_table(catalog_list: list[dict], total_items: int) -> None:
    """Merender tabel katalog, pagination, tombol aksi, dan ekspor PDF."""
    
    summary_col, _ = st.columns([1, 3])
    with summary_col:
        if st.button("✨ Ringkasan AI Global (Summary)", use_container_width=True, type="secondary"):
            show_ai_summary_modal()

    st.divider()
    
    title_col, export_col = st.columns([3, 1])
    with title_col:
        st.markdown("### 📋 Katalog Rules Keamanan & Aksi Eksekusi")
    with export_col:
        _render_pdf_export()

    total_pages = max(1, math.ceil(total_items / ITEMS_PER_PAGE))
    current_page = min(max(int(st.session_state.get("page_num", 1)), 1), total_pages)
    if current_page != st.session_state.get("page_num", 1):
        st.session_state.page_num = current_page

    nav_col, _, total_col = st.columns([2, 6, 2])
    with nav_col:
        selected_page = st.number_input(
            "Halaman",
            min_value=1,
            max_value=total_pages,
            value=current_page,
            step=1,
            key="page_input_num",
        )
        if int(selected_page) != current_page:
            st.session_state.page_num = int(selected_page)
            st.rerun()

    with total_col:
        st.markdown(
            f"<div style='text-align:right;padding-top:28px;color:#8e8f99'>"
            f"Total: {total_items} rules</div>",
            unsafe_allow_html=True,
        )

    st.divider()
    if not catalog_list:
        st.info("Belum ada data katalog. Pastikan backend API aktif atau lakukan sinkronisasi.")
        return

    widths = [0.8, 1.6, 2.6, 2.2, 1.2, 1.2, 3.6]
    headers = ["ID", "Nama Kontrol", "Kode CIS & Judul CIS", "Regulasi & Kepatuhan", "Kategori", "Status Audit", "Aksi"]
    for column, heading in zip(st.columns(widths), headers):
        with column:
            st.markdown(f"**{heading}**")

    st.divider()
    for index, item in enumerate(catalog_list):
        rule_id = item.get("id", "-")
        nama = item.get("nama", "-")
        kode_cis = item.get("kode_cis", "-")
        #judul_cis = _catalog_value(item, "judul_cis", "cis_judul")
        judul_cis = item.get("judul_cis", "-")
        regulasi = item.get("regulasi", "-")
        kepatuhan = item.get("kepatuhan", "-")
        kategori = item.get("kategori", "-")
        status = item.get("status_audit", "PENDING")

        columns = st.columns(widths)
        with columns[0]:
            st.write(rule_id)
        with columns[1]:
            st.write(nama)
        with columns[2]:
            if (not kode_cis or kode_cis == "-") and (not judul_cis or judul_cis == "-"):
                st.markdown("**`Non-CIS`** — Aturan Kustom")
            else:
                st.markdown(f"**`{kode_cis}`** — {judul_cis}")
        with columns[3]:
            st.markdown(
                f"**{regulasi}**<br><small style='color: gray;'>({kepatuhan})</small>", 
                unsafe_allow_html=True
            )
        with columns[4]:
            st.write(kategori)
        with columns[5]:
            _render_status_badge(status)
        with columns[6]:
            _render_catalog_actions(item, index)

        st.markdown(
            "<hr style='margin:4px 0;border-color:#2d2f3d'>",
            unsafe_allow_html=True,
        )

    st.caption(f"Halaman {current_page} dari {total_pages}")
