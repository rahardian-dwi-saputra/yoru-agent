#!/bin/bash

set -e

echo "=== Pembuatan Virtual Environment FastAPI ==="

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Script berada di project/setup/, venv & key akan dibuat di project/api/
API_KEY_PATH=$(python3 -c "import sys; sys.path.insert(0, '$PROJECT_DIR'); from config.settings import API_KEY_PATH; print(API_KEY_PATH)")

API_DIR="$(dirname "$API_KEY_PATH")"
VENV_DIR="$API_DIR/venv"

# Buat folder project/api jika belum ada
mkdir -p "$API_DIR"

if [ -d "$VENV_DIR" ]; then
    echo "Virtual environment sudah ada di: $VENV_DIR"
else
    echo "Membuat virtual environment di: $VENV_DIR ..."
    python3 -m venv "$VENV_DIR"
    echo "Virtual environment berhasil dibuat."
fi

# Aktivasi venv dan perbarui pip/instal FastAPI
echo "Mengaktifkan venv dan menginstal packages dasar..."
source "$VENV_DIR/bin/activate"

pip install --upgrade pip
pip install fastapi uvicorn slowapi pyyaml

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
echo "Untuk mengaktifkan virtual environment secara manual, jalankan:"
echo "source $VENV_DIR/bin/activate"