#!/bin/bash

set -e

echo "=== Pembuatan Virtual Environment FastAPI ==="

# Script berada di project/setup/, venv & key akan dibuat di project/api/
API_DIR="$(cd "$(dirname "$0")/../api" && pwd)"
VENV_DIR="$API_DIR/venv"
KEY_FILE="$API_DIR/key.txt"

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

if [ -f "$KEY_FILE" ]; then
    echo "API Key sudah ada di: $KEY_FILE"
else
    echo "Meng-generate API Key baru..."
    
    # Prioritaskan openssl, fallback ke python secrets jika openssl tidak tersedia
    if command -v openssl >/dev/null 2>&1; then
        GENERATED_KEY=$(openssl rand -hex 32)
    else
        GENERATED_KEY=$(python3 -c "import secrets; print(secrets.token_hex(32))")
    fi

    # Simpan API Key ke file key.txt
    echo "$GENERATED_KEY" > "$KEY_FILE"
    
    # Set hak akses file agar hanya pengguna/owner yang bisa membaca (Security Best Practice)
    chmod 600 "$KEY_FILE"
    
    echo "API Key berhasil digenerate dan disimpan ke: $KEY_FILE"
fi

echo ""
echo "=================================================================="
echo " API KEY ANDA : $(cat "$KEY_FILE")"
echo " (Simpan API Key ini untuk mengakses endpoint API)"
echo "=================================================================="

echo ""
echo "=== Selesai! ==="
echo "Untuk mengaktifkan virtual environment secara manual, jalankan:"
echo "source $VENV_DIR/bin/activate"