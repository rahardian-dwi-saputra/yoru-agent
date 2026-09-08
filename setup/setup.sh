#!/bin/bash

# Hentikan eksekusi jika terjadi error
set -e

echo "=== 1. Pengecekan Hermes Agent ==="
if command -v hermes-agent &> /dev/null; then
    echo -n "Hermes Agent sudah terpasang! Versi: "
    hermes-agent --version 2>&1 || hermes-agent -v 2>&1
else
    echo "Hermes Agent belum terpasang di sistem ini."
fi

echo ""
echo "=== 2. Pembuatan Virtual Environment FastAPI ==="

# Menentukan path target relatif dari script ini
# Script berada di project/setup/, venv akan dibuat di project/api/venv
API_DIR="$(dirname "$0")/../api"
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
pip install fastapi uvicorn

echo ""
echo "=== Selesai! ==="
echo "Untuk mengaktifkan virtual environment secara manual, jalankan:"
echo "source project/api/venv/bin/activate"