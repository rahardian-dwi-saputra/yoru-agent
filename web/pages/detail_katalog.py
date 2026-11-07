from __future__ import annotations

from datetime import datetime
from typing import Any

import pandas as pd
import streamlit as st

from database import get_catalog_detail
from services import fetch_catalog_logs


st.set_page_config(
    page_title="Detail Katalog | Yoru-Agent",
    page_icon="🛡️",
    layout="wide",
)


LOG_TYPES = {
    "Audit": "audit",
    "Hardening": "hardening",
    "Rollback": "rollback",
}


def _as_bool(value: Any) -> bool:
    """Mengubah nilai database menjadi boolean dengan aman."""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "ya"}
    return False


def format_timestamp(value: Any) -> str:
    """Memformat timestamp log."""
    if not value:
        return "-"

    try:
        timestamp = datetime.fromisoformat(str(value))
        return timestamp.strftime("%d-%m-%Y %H:%M:%S")
    except (ValueError, TypeError):
        return str(value)


def load_catalog_logs(
    catalog_id: str,
    audit_only: bool = False,
) -> tuple[dict[str, list[dict]], dict[str, str]]:
    """Mengambil log katalog; katalog audit-only hanya mengambil log audit."""
    logs_by_type: dict[str, list[dict]] = {}
    errors: dict[str, str] = {}

    allowed_types = {"Audit": "audit"} if audit_only else LOG_TYPES

    for log_type in allowed_types.values():
        success, logs, error = fetch_catalog_logs(catalog_id, log_type)

        logs_by_type[log_type] = logs if success else []
        if not success:
            errors[log_type] = error or "Gagal mengambil log dari API."

    return logs_by_type, errors


def build_duration_dataframe(
    logs_by_type: dict[str, list[dict]],
) -> pd.DataFrame:
    """Membentuk data grafik: satu titik untuk setiap execution_id."""
    chart_rows = []

    for log_type, logs in logs_by_type.items():
        executions: dict[str, list[dict]] = {}

        for log in logs:
            execution_id = log.get("execution_id")
            if not execution_id:
                continue

            executions.setdefault(str(execution_id), []).append(log)

        for execution_logs in executions.values():
            # Urutkan log dalam satu eksekusi berdasarkan timestamp.
            execution_logs.sort(
                key=lambda item: str(item.get("timestamp") or "")
            )

            # Pilih log Result yang memiliki duration_ms.
            result_logs = [
                log
                for log in execution_logs
                if str(log.get("step", "")).lower() == "result"
                and log.get("duration_ms") is not None
            ]

            # Jika Result tidak memiliki duration_ms, gunakan log
            # terakhir dalam eksekusi yang memiliki duration_ms.
            duration_logs = [
                log
                for log in execution_logs
                if log.get("duration_ms") is not None
            ]

            selected_log = (
                result_logs[-1]
                if result_logs
                else duration_logs[-1] if duration_logs else None
            )

            if selected_log is None:
                continue

            try:
                duration = float(selected_log["duration_ms"])
                timestamp = pd.to_datetime(
                    selected_log.get("timestamp"),
                    errors="coerce",
                )
            except (TypeError, ValueError, KeyError):
                continue

            if pd.isna(timestamp):
                continue

            chart_rows.append(
                {
                    "Waktu": timestamp,
                    "Jenis": log_type,
                    "Durasi (ms)": duration,
                }
            )

    if not chart_rows:
        return pd.DataFrame()

    data = pd.DataFrame(chart_rows)

    # Timestamp menjadi sumbu X. pivot_table juga menangani kemungkinan
    # timestamp identik pada jenis aktivitas yang sama.
    chart = data.pivot_table(
        index="Waktu",
        columns="Jenis",
        values="Durasi (ms)",
        aggfunc="last",
    ).sort_index()

    # Urutan seri pada grafik dibuat konsisten.
    ordered_columns = [
        log_type
        for log_type in LOG_TYPES.values()
        if log_type in chart.columns
    ]

    return chart[ordered_columns]


def render_duration_chart(
    logs_by_type: dict[str, list[dict]],
) -> None:
    """Menampilkan grafik durasi audit, hardening, dan rollback."""
    st.subheader("⏱️ Grafik Durasi Eksekusi")

    chart_data = build_duration_dataframe(logs_by_type)

    if chart_data.empty:
        st.info("Belum tersedia data duration_ms untuk ditampilkan.")
        return

    st.line_chart(
        chart_data,
        height=350,
        y_label="Durasi (ms)",
    )

    st.caption(
        "Setiap titik mewakili satu eksekusi (execution_id). "
        "Durasi diambil dari log Result jika tersedia; "
        "jika tidak, digunakan log terakhir yang memiliki duration_ms."
    )


def render_catalog_information(detail: dict) -> None:
    """Menampilkan informasi dan metadata katalog."""
    st.title(f"📄 Detail Katalog: {detail.get('id', '-')}")

    st.subheader(detail.get("nama") or "-")
    st.caption(detail.get("deskripsi") or "-")

    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Kode CIS", detail.get("kode_cis") or "-")
        st.write("**Judul CIS**")
        st.write(detail.get("judul_cis") or "-")

    with col2:
        st.metric("Risiko", detail.get("risiko") or "-")
        st.write("**Kategori**")
        st.write(detail.get("kategori") or "-")

    with col3:
        st.metric(
            "Audit Only",
            "Ya" if _as_bool(detail.get("audit_only")) else "Tidak",
        )
        st.write("**Versi CIS**")
        st.write(detail.get("versi_cis") or "-")

    st.divider()

    col1, col2 = st.columns(2)

    with col1:
        st.write("**Framework**")
        st.write(detail.get("framework") or "-")

        st.write("**Regulasi**")
        st.write(detail.get("regulasi") or "-")

    with col2:
        st.write("**Kepatuhan**")
        st.write(detail.get("kepatuhan") or "-")


def render_log_entry(log: dict) -> None:
    """Menampilkan satu entri log."""
    status = str(log.get("status") or "UNKNOWN").upper()

    status_icons = {
        "COMPLIANT": "🟢",
        "SUCCESS": "🟢",
        "SKIPPED": "🔵",
        "INFO": "🔵",
        "NON_COMPLIANT": "🟡",
        "WARNING": "🟡",
        "ERROR": "🔴",
        "FAILED": "🔴",
    }

    icon = status_icons.get(status, "⚪")

    with st.expander(
        f"{icon} {status} | {log.get('step', '-')} "
        f"| {format_timestamp(log.get('timestamp'))}",
        expanded=False,
    ):
        col1, col2 = st.columns(2)

        with col1:
            st.write("**Execution ID**")
            st.code(log.get("execution_id") or "-")

            st.write("**Hostname**")
            st.write(log.get("hostname") or "-")

            st.write("**Executed By**")
            st.write(log.get("executed_by") or "-")

        with col2:
            st.write("**PID**")
            st.write(str(log.get("pid") or "-"))

            st.write("**Timezone**")
            st.write(log.get("timezone") or "-")

            st.write("**Durasi**")
            duration = log.get("duration_ms")

            try:
                st.write(
                    f"{float(duration):.2f} ms"
                    if duration is not None
                    else "-"
                )
            except (TypeError, ValueError):
                st.write("-")

        st.write("**Pesan Log**")
        st.code(log.get("message") or "-", language=None)


def render_log_history(
    logs_by_type: dict[str, list[dict]],
    errors: dict[str, str],
) -> None:
    """Menampilkan riwayat log untuk ketiga jenis aktivitas."""
    tabs = st.tabs(list(LOG_TYPES.keys()))

    for tab, (label, log_type) in zip(tabs, LOG_TYPES.items()):
        with tab:
            if st.button(
               f"🔄 Refresh Log {label}",
                key=f"refresh_{log_type}",
            ):
                st.rerun()

            if log_type in errors:
                st.error(errors[log_type])
                continue

            logs = logs_by_type.get(log_type, [])

            if not logs:
                st.info(f"Belum ada riwayat log {label.lower()}.")
                continue

            st.caption(f"Total: {len(logs)} entri log")

            # Riwayat ditampilkan dari waktu terbaru.
            sorted_logs = sorted(
                logs,
                key=lambda item: str(item.get("timestamp") or ""),
                reverse=True,
            )

            for log in sorted_logs:
                render_log_entry(log)


def main() -> None:
    """Halaman utama detail katalog."""
    catalog_id = st.session_state.get("selected_catalog_id")

    if not catalog_id:
        st.warning("Tidak ada katalog yang dipilih.")
        if st.button("Kembali ke Dashboard"):
            st.switch_page("app.py")
        return

    detail = get_catalog_detail(catalog_id)

    if not detail:
        st.error(f"Katalog {catalog_id} tidak ditemukan.")
        if st.button("Kembali ke Dashboard"):
            st.switch_page("app.py")
        return

    if st.button("🔙 Kembali ke Dashboard"):
        st.switch_page("app.py")

    st.divider()

    render_catalog_information(detail)

    audit_only = _as_bool(detail.get("audit_only"))
    if audit_only:
        st.info(
            "Katalog ini hanya mendukung operasi audit. "
            "Log hardening dan rollback tidak ditampilkan karena "
            "operasi tersebut berpotensi mengganggu layanan server "
            "yang sedang berjalan."
        )

    # Ambil log satu kali, lalu gunakan data yang sama untuk grafik
    # dan riwayat log agar tidak melakukan request API berulang.
    with st.spinner("Mengambil riwayat aktivitas katalog..."):
        logs_by_type, errors = load_catalog_logs(
            catalog_id,
            audit_only=audit_only,
        )

    st.divider()
    render_duration_chart(logs_by_type)

    st.divider()
    st.subheader("📜 Riwayat Log Eksekusi")
    render_log_history(logs_by_type, errors)


if __name__ == "__main__":
    main()
