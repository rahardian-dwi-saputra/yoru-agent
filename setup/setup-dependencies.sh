#!/bin/bash

set -e

echo "=== Pembuatan Virtual Environment Terpusat (Root Proyek) ==="

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

VENV_DIR="$PROJECT_DIR/venv"

# Lokasi API Key tetap diatur via config.api (biasanya di dalam folder api/)
API_KEY_PATH=$(python3 -c "import sys; sys.path.insert(0, '$PROJECT_DIR'); from config.api import API_KEY_PATH; print(API_KEY_PATH)")
API_DIR="$(dirname "$API_KEY_PATH")"

# Buat folder api jika belum ada (untuk tempat penyimpanan key/database)
mkdir -p "$API_DIR"

if [ -d "$VENV_DIR" ]; then
    echo "Virtual environment sudah ada di: $VENV_DIR"
else
    echo "Membuat virtual environment di root proyek: $VENV_DIR ..."
    python3 -m venv "$VENV_DIR"
    echo "Virtual environment berhasil dibuat."
fi

# Aktivasi venv dan perbarui pip/instal packages (FastAPI, Uvicorn, Streamlit, dll)
echo "Mengaktifkan venv dan menginstal packages (Backend & Web Dashboard)..."
source "$VENV_DIR/bin/activate"

pip install --upgrade pip
pip install fastapi uvicorn slowapi pyyaml streamlit requests

# === GENERATE API KEY ===
echo ""
echo "=== Konfigurasi API Key ==="

if [ -f "$API_KEY_PATH" ]; then
    echo "API Key sudah ada di: $API_KEY_PATH"
else
    echo "Meng-generate API Key baru..."
    
    # Prioritaskan openssl, fallback ke python secrets jika openssl tidak tersedia
    if command -v openssl >/dev/null 2>&1; then
        GENERATED_KEY=$(openssl rand -hex 32)
    else
        GENERATED_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    fi

    # Simpan API Key ke file key.txt
    echo "$GENERATED_KEY" > "$API_KEY_PATH"
    
    # Set hak akses file agar hanya pengguna/owner yang bisa membaca (Security Best Practice)
    chmod 600 "$API_KEY_PATH"
    
    echo "API Key berhasil digenerate dan disimpan ke: $API_KEY_PATH"
fi

echo ""
echo "=================================================================="
echo " API KEY ANDA : $(cat "$API_KEY_PATH")"
echo " (Simpan API Key ini untuk mengakses endpoint API)"
echo "=================================================================="

echo ""
echo "=== Selesai! ==="
echo "Virtual environment terpusat siap digunakan."
echo "Untuk mengaktifkan secara manual, jalankan:"
echo "source venv/bin/activate"