from __future__ import annotations
from contextlib import closing
from pathlib import Path
from typing import Any
import sqlite3


DB_PATH = Path(__file__).resolve().with_name("web_cache.db")

CATALOG_FIELDS = (
    "nama",
    "kode_cis",
    "judul_cis",
    "versi_cis",
    "regulasi",
    "kepatuhan",
    "framework",
    "deskripsi",
    "risiko",
    "kategori",
    "audit_only",
    "pesan_hardening",
    "pesan_rollback",
)

REQUIRED_CATALOG_FIELDS = ("id", "nama", "deskripsi", "risiko", "kategori")

STATUS_COLUMNS = {
    "audit": ("status_audit", "waktu_audit"),
    "hardening": ("status_hardening", "waktu_hardening"),
    "rollback": ("status_rollback", "waktu_rollback"),
}

def _connect() -> sqlite3.Connection:
    """Membuat koneksi SQLite dengan row mapping dan foreign key aktif."""
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _to_bool(value: Any) -> int:
    """Mengubah nilai boolean dari API menjadi 0 atau 1."""
    if isinstance(value, str):
        return int(value.strip().lower() in {"1", "true", "yes", "ya"})
    return int(bool(value))


def init_db() -> None:
    """Membuat tabel database jika belum tersedia."""
    with closing(_connect()) as conn:
        with conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS servers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sistem_operasi TEXT NOT NULL,
                    arsitektur TEXT NOT NULL,
                    hostname TEXT
                )
                """
            )

            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS catalogs (
                    id TEXT PRIMARY KEY,
                    server_id INTEGER NOT NULL,
                    nama TEXT NOT NULL,
                    kode_cis TEXT,
                    judul_cis TEXT,
                    versi_cis TEXT,
                    regulasi TEXT,
                    kepatuhan TEXT,
                    framework TEXT,
                    deskripsi TEXT NOT NULL,
                    risiko TEXT NOT NULL,
                    kategori TEXT NOT NULL,
                    audit_only BOOLEAN NOT NULL DEFAULT 0,
                    pesan_hardening TEXT,
                    pesan_rollback TEXT,
                    status_audit TEXT DEFAULT 'Pending',
                    waktu_audit TIMESTAMP,
                    log_audit_terakhir TEXT,
                    status_hardening TEXT DEFAULT 'Pending',
                    waktu_hardening TIMESTAMP,
                    log_hardening_terakhir TEXT,
                    status_rollback TEXT DEFAULT 'Pending',
                    waktu_rollback TIMESTAMP,
                    log_rollback_terakhir TEXT,
                    FOREIGN KEY (server_id) REFERENCES servers (id)
                        ON DELETE CASCADE
                )
                """
            )

            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_catalogs_nama ON catalogs(nama)"
            )


def _get_or_create_server(
    conn: sqlite3.Connection,
    server_info: dict[str, Any] | None = None,
) -> int:
    """Mengambil server pertama atau membuat record server awal."""
    info = server_info or {}
    sistem_operasi = info.get("os_platform") or info.get("sistem_operasi")
    arsitektur = info.get("architecture") or info.get("arsitektur")
    hostname = info.get("hostname")

    row = conn.execute(
        "SELECT id FROM servers ORDER BY id LIMIT 1"
    ).fetchone()

    if row:
        server_id = row["id"]
        if sistem_operasi or arsitektur:
            conn.execute(
                """
                UPDATE servers
                SET sistem_operasi = ?, arsitektur = ?, hostname = ?
                WHERE id = ?
                """,
                (
                    sistem_operasi or "Tidak diketahui",
                    arsitektur or "Tidak diketahui",
                    hostname or "Tidak diketahui",
                    server_id,
                ),
            )
        return server_id

    cursor = conn.execute(
        """
        INSERT INTO servers (sistem_operasi, arsitektur, hostname)
        VALUES (?, ?, ?)
        """,
        (
            sistem_operasi or "Tidak diketahui",
            arsitektur or "Tidak diketahui",
            hostname or "Tidak diketahui",
        ),
    )
    return int(cursor.lastrowid)


def save_server_info(server_info: dict[str, Any]) -> int:
    """Menyimpan atau memperbarui informasi server."""

    with closing(_connect()) as conn:
        with conn:
            return _get_or_create_server(conn, server_info)

        
def save_or_update_catalogs(
    catalogs_list: list[dict[str, Any]],
    server_info: dict[str, Any] | None = None,
) -> None:
    """
    Menyinkronkan katalog dari API ke database lokal.

    Data katalog diperbarui jika ID sudah ada. Status, waktu, dan log
    audit/hardening/rollback yang sudah tersimpan tidak ditimpa.
    """
    if not catalogs_list:
        return

    columns = ", ".join(CATALOG_FIELDS)
    placeholders = ", ".join("?" for _ in CATALOG_FIELDS)
    update_clause = ", ".join(
        f"{field} = excluded.{field}" for field in CATALOG_FIELDS
    )

    query = f"""
        INSERT INTO catalogs (id, server_id, {columns})
        VALUES (?, ?, {placeholders})
        ON CONFLICT(id) DO UPDATE SET
            server_id = excluded.server_id,
            {update_clause}
    """

    with closing(_connect()) as conn:
        with conn:
            server_id = _get_or_create_server(conn, server_info)

            for index, item in enumerate(catalogs_list, start=1):
                missing = [
                    field
                    for field in REQUIRED_CATALOG_FIELDS
                    if item.get(field) in (None, "")
                ]
                if missing:
                    raise ValueError(
                        f"Data katalog ke-{index} tidak lengkap. "
                        f"Field wajib: {', '.join(missing)}."
                    )

                values = []
                for field in CATALOG_FIELDS:
                    value = item.get(field)
                    if field == "audit_only":
                        value = _to_bool(value)
                    values.append(value)

                conn.execute(query, (str(item["id"]), server_id, *values))


def get_paginated_catalogs(
    page: int = 1,
    per_page: int = 10,
) -> tuple[list[dict[str, Any]], int]:
    """Mengambil katalog berdasarkan halaman dan jumlah data per halaman."""
    page = max(1, int(page))
    per_page = max(1, int(per_page))
    offset = (page - 1) * per_page

    with closing(_connect()) as conn:
        total_items = conn.execute(
            "SELECT COUNT(*) FROM catalogs"
        ).fetchone()[0]

        rows = conn.execute(
            """
            SELECT *
            FROM catalogs
            ORDER BY id
            LIMIT ? OFFSET ?
            """,
            (per_page, offset),
        ).fetchall()

    return [dict(row) for row in rows], total_items


def update_execution_status(
    rule_id: str,
    action_type: str,
    status: str,
    timestamp: str,
) -> bool:
    """
    Memperbarui status dan waktu eksekusi katalog.

    Mengembalikan True jika katalog ditemukan dan berhasil diperbarui.
    """
    action = action_type.strip().lower()
    if action not in STATUS_COLUMNS:
        raise ValueError(
            "action_type harus berupa 'audit', 'hardening', atau 'rollback'."
        )

    status_column, timestamp_column = STATUS_COLUMNS[action]

    with closing(_connect()) as conn:
        with conn:
            cursor = conn.execute(
                f"""
                UPDATE catalogs
                SET {status_column} = ?, {timestamp_column} = ?
                WHERE id = ?
                """,
                (status, timestamp, rule_id),
            )

    return cursor.rowcount > 0


def get_dashboard_metrics() -> dict[str, int]:
    """Menghitung total dan keberhasilan audit, hardening, serta rollback."""
    with closing(_connect()) as conn:
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS total_audit_roles,
                SUM(CASE
                    WHEN status_audit = 'COMPLIANT' THEN 1 ELSE 0
                END) AS total_audit_berhasil,
                SUM(CASE
                    WHEN audit_only = 0 THEN 1 ELSE 0
                END) AS total_hardening_roles,
                SUM(CASE
                    WHEN audit_only = 0
                     AND status_hardening IN ('SKIPPED', 'SUCCESS')
                    THEN 1 ELSE 0
                END) AS total_hardening_berhasil,
                SUM(CASE
                    WHEN audit_only = 0
                     AND status_rollback IN ('SKIPPED', 'SUCCESS')
                    THEN 1 ELSE 0
                END) AS total_rollback_berhasil
            FROM catalogs
            """
        ).fetchone()

    total_hardening_roles = row["total_hardening_roles"] or 0

    return {
        "total_audit_roles": row["total_audit_roles"] or 0,
        "total_audit_berhasil": row["total_audit_berhasil"] or 0,
        "total_hardening_roles": total_hardening_roles,
        "total_hardening_berhasil": row["total_hardening_berhasil"] or 0,
        "total_rollback_roles": total_hardening_roles,
        "total_rollback_berhasil": row["total_rollback_berhasil"] or 0,
    }


def get_server_info() -> dict[str, Any] | None:
    """Mengambil detail server yang tersimpan di database."""
    conn = _connect()

    try:
        cursor = conn.execute(
            """
            SELECT
                id,
                sistem_operasi,
                arsitektur,
                hostname
            FROM servers
            ORDER BY id DESC
            LIMIT 1
            """
        )

        row = cursor.fetchone()

        if row is None:
            return None

        columns = [column[0] for column in cursor.description]
        return dict(zip(columns, row))

    finally:
        conn.close()


def get_catalog_detail(rule_id: str) -> dict[str, Any] | None:
    """Mengambil detail satu katalog berdasarkan ID."""
    with closing(_connect()) as conn:
        row = conn.execute(
            "SELECT * FROM catalogs WHERE id = ?",
            (rule_id,),
        ).fetchone()

    return dict(row) if row else None