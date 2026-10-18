import os
import sqlite3

DB_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "web_cache.db"
)


def init_db():
  """Inisialisasi database SQLite """
  conn = sqlite3.connect(DB_PATH)
  cursor = conn.cursor()

  cursor.execute("""
        CREATE TABLE IF NOT EXISTS catalogs (
            id TEXT PRIMARY KEY,
            nama TEXT NOT NULL,
            kode_cis TEXT NOT NULL,
            cis_judul TEXT NOT NULL,
            deskripsi TEXT NOT NULL,
            resiko TEXT NOT NULL,
            kategori TEXT NOT NULL,
            audit_only BOOLEAN NOT NULL,
            status_audit TEXT DEFAULT 'Pending',
            waktu_audit TEXT DEFAULT '-',
            status_hardening TEXT DEFAULT 'Pending',
            waktu_hardening TEXT DEFAULT '-',
            status_rollback TEXT DEFAULT 'Pending',
            waktu_rollback TEXT DEFAULT '-'
        )
    """)

  conn.commit()
  conn.close()


def save_or_update_catalogs(catalogs_list):
  """Melakukan sinkronisasi data katalog:

  - UPDATE jika ID sudah ada (tanpa menimpa status eksekusi)
  - INSERT jika ID belum ada
  """
  if not catalogs_list:
    return

  conn = sqlite3.connect(DB_PATH)
  cursor = conn.cursor()

  for item in catalogs_list:
    rule_id = item.get("id")
    nama = item.get("nama")
    kode_cis = item.get("kode_cis")
    cis_judul = item.get("cis_judul")
    deskripsi = item.get("deskripsi")
    resiko = item.get("resiko")
    kategori = item.get("kategori")
    audit_only = 1 if item.get("audit_only") else 0

    cursor.execute("SELECT id FROM catalogs WHERE id = ?", (rule_id,))
    exists = cursor.fetchone()

    if exists:
      cursor.execute(
          """
                UPDATE catalogs 
                SET nama = ?, kode_cis = ?, cis_judul = ?, deskripsi = ?, resiko = ?, kategori = ?, audit_only = ?
                WHERE id = ?
            """,
          (
              nama,
              kode_cis,
              cis_judul,
              deskripsi,
              resiko,
              kategori,
              audit_only,
              rule_id,
          ),
      )
    else:
      cursor.execute(
          """
                INSERT INTO catalogs (
                    id, nama, kode_cis, cis_judul, deskripsi, resiko, kategori, audit_only,
                    status_audit, waktu_audit, status_hardening, waktu_hardening, status_rollback, waktu_rollback
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Pending', '-', 'Pending', '-', 'Pending', '-')
            """,
          (
              rule_id,
              nama,
              kode_cis,
              cis_judul,
              deskripsi,
              resiko,
              kategori,
              audit_only,
          ),
      )

  conn.commit()
  conn.close()


def get_paginated_catalogs(page: int = 1, per_page: int = 10):
  """Mengambil data katalog dengan pagination SQL."""
  conn = sqlite3.connect(DB_PATH)
  conn.row_factory = sqlite3.Row
  cursor = conn.cursor()

  offset = (page - 1) * per_page

  cursor.execute("SELECT COUNT(*) FROM catalogs")
  total_items = cursor.fetchone()[0]

  cursor.execute("SELECT * FROM catalogs LIMIT ? OFFSET ?", (per_page, offset))
  rows = cursor.fetchall()

  conn.close()

  return [dict(row) for row in rows], total_items


def update_execution_status(
    rule_id: str, action_type: str, status: str, timestamp: str
):
  """Memperbarui status dan waktu eksekusi (audit, hardening, atau rollback)."""
  conn = sqlite3.connect(DB_PATH)
  cursor = conn.cursor()

  if action_type == "audit":
    cursor.execute(
        "UPDATE catalogs SET status_audit = ?, waktu_audit = ? WHERE id = ?",
        (status, timestamp, rule_id),
    )
  elif action_type == "hardening":
    cursor.execute(
        "UPDATE catalogs SET status_hardening = ?, waktu_hardening = ? WHERE"
        " id = ?",
        (status, timestamp, rule_id),
    )
  elif action_type == "rollback":
    cursor.execute(
        "UPDATE catalogs SET status_rollback = ?, waktu_rollback = ? WHERE id = ?",
        (status, timestamp, rule_id),
    )

  conn.commit()
  conn.close()


def get_dashboard_metrics():
  """Menghitung metrik statistik untuk dashboard sesuai kriteria:

  - Total role audit = total katalog
  - Total audit berhasil = katalog dengan status_audit = 'COMPLIANT'
  - Total role hardening = total katalog - katalog dengan audit_only = true
  - Total hardening berhasil = katalog dengan status_hardening IN ('SKIPPED', 'SUCCESS')
  - Total role rollback = total katalog - katalog dengan audit_only = true
  - Total rollback berhasil = katalog dengan status_rollback IN ('SKIPPED', 'SUCCESS')
  """
  conn = sqlite3.connect(DB_PATH)
  cursor = conn.cursor()

  # 1. Total katalog keseluruhan
  cursor.execute("SELECT COUNT(*) FROM catalogs")
  total_katalog = cursor.fetchone()[0]

  # 2. Total audit berhasil (status_audit = 'COMPLIANT')
  cursor.execute(
      "SELECT COUNT(*) FROM catalogs WHERE status_audit = 'COMPLIANT'"
  )
  total_audit_berhasil = cursor.fetchone()[0]

  # 3. Total role hardening (total katalog - audit_only = true)
  cursor.execute("SELECT COUNT(*) FROM catalogs WHERE audit_only = 0")
  total_role_hardening = cursor.fetchone()[0]

  # 4. Total hardening berhasil (status_hardening 'SKIPPED' atau 'SUCCESS' dan bukan audit_only)
  cursor.execute(
      "SELECT COUNT(*) FROM catalogs WHERE audit_only = 0 AND status_hardening"
      " IN ('SKIPPED', 'SUCCESS')"
  )
  total_hardening_berhasil = cursor.fetchone()[0]

  # 5. Total role rollback (sama seperti hardening, yaitu total katalog - audit_only = true)
  total_role_rollback = total_role_hardening

  # 6. Total rollback berhasil (status_rollback 'SKIPPED' atau 'SUCCESS' dan bukan audit_only)
  cursor.execute(
      "SELECT COUNT(*) FROM catalogs WHERE audit_only = 0 AND status_rollback IN"
      " ('SKIPPED', 'SUCCESS')"
  )
  total_rollback_berhasil = cursor.fetchone()[0]

  conn.close()

  return {
      "total_audit_roles": total_katalog,
      "total_audit_berhasil": total_audit_berhasil,
      "total_hardening_roles": total_role_hardening,
      "total_hardening_berhasil": total_hardening_berhasil,
      "total_rollback_roles": total_role_rollback,
      "total_rollback_berhasil": total_rollback_berhasil,
  }


def get_catalog_detail(rule_id: str):
    """Mengambil detail lengkap satu katalog berdasarkan ID rule."""
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute("SELECT * FROM catalogs WHERE id = ?", (rule_id,))
    row = cursor.fetchone()
    
    conn.close()
    
    if row:
        return dict(row)
    return None