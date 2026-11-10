#!/bin/bash

set -Eeuo pipefail

# Pastikan script dijalankan dengan hak akses root
if [[ "$EUID" -ne 0 ]]; then
    echo "[-] Harap jalankan skrip ini dengan sudo: sudo bash install.sh"
    exit 1
fi

echo "=========================================================="
echo "          MEMULAI INSTALASI LENGKAP YORU-AGENT            "
echo "=========================================================="

PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

# Validasi file instalasi
ENV_SCRIPT="$PROJECT_DIR/setup/setup-environment.sh"
DEPENDENCY_SCRIPT="$PROJECT_DIR/setup/setup-dependencies.sh"
START_SCRIPT="$PROJECT_DIR/start-yoru-agent.sh"

for script in "$ENV_SCRIPT" "$DEPENDENCY_SCRIPT"; do
    if [[ ! -f "$script" ]]; then
        echo "[-] File instalasi tidak ditemukan: $script"
        exit 1
    fi
done

# LANGKAH 1: Setup System Environment, User, dan Sudoers
echo ""
echo "[Langkah 1/2] Menyiapkan environment sistem dan hak akses..."

bash "$ENV_SCRIPT"

# LANGKAH 2: Setup Python Virtual Environment & API Key
echo ""
echo "[Langkah 2/2] Menyiapkan Python Virtual Environment & API Key..."

bash "$DEPENDENCY_SCRIPT"

# LANGKAH 3: Menyiapkan izin script untuk menjalankan aplikasi
if [[ -f "$START_SCRIPT" ]]; then
    chmod 755 "$START_SCRIPT"
    echo "[OK] Script menjalankan API dan Dashboard siap digunakan."
else
    echo "[INFO] start-yoru-agent.sh belum tersedia."
fi

echo ""
echo "=========================================================="
echo "          INSTALASI YORU-AGENT BERHASIL SELESAI!          "
echo "=========================================================="
echo ""
echo "Untuk menjalankan aplikasi:"
echo "  ./start-yoru-agent.sh start"
echo ""
echo "Untuk memeriksa status:"
echo "  ./start-yoru-agent.sh status"
echo ""
echo "Untuk menghentikan aplikasi:"
echo "  ./start-yoru-agent.sh stop"
echo ""