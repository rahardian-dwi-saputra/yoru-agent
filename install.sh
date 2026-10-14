#!/bin/bash

set -e

# Pastikan script dijalankan dengan hak akses root/sudo
if [ "$EUID" -ne 0 ]; then
  echo "[-] Harap jalankan skrip ini dengan sudo: sudo bash install.sh"
  exit 1
fi

echo "=========================================================="
echo "          MEMULAI INSTALASI LENGKAP YORU-AGENT            "
echo "=========================================================="

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# LANGKAH 1: Setup System Environment, User, dan Sudoers
echo ""
echo "[Langkah 1/2] Menyiapkan environment sistem dan hak akses..."
bash "$PROJECT_DIR/deploy/setup-environment.sh"

# LANGKAH 2: Setup Python Virtual Environment & API Key
echo ""
echo "[Langkah 2/2] Menyiapkan Python Virtual Environment & API Key..."
# Jalankan skrip setup API (pastikan dijalankan agar kepemilikan tetap aman)
bash "$PROJECT_DIR/deploy/setup-api.sh"

# Pastikan ulang kepemilikan folder proyek dipegang oleh yoru-agent setelah venv terbuat
chown -R yoru-agent:yoru-agent "$PROJECT_DIR"

echo ""
echo "=========================================================="
echo "          INSTALASI YORU-AGENT BERHASIL SELESAI!          "
echo "=========================================================="
echo "Anda sekarang dapat menjalankan agen atau layanan FastAPI."