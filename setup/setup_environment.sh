#!/bin/bash

set -e

echo "=== Pembuatan Virtual Environment FastAPI ==="

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
echo "source yoru-agent/api/venv/bin/activate"