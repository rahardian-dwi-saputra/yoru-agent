#!/usr/bin/env bash

set -Eeuo pipefail

# Pastikan script dijalankan sebagai root
if [[ "$EUID" -ne 0 ]]; then
    echo "[-] Jalankan skrip ini menggunakan sudo atau sebagai root!"
    exit 1
fi

TARGET_USER="yoru-agent"
PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"

SUDOERS_FILE="/etc/sudoers.d/yoru-agent"
START_SCRIPT="$PROJECT_DIR/start-yoru-agent.sh"
VENV_DIR="$PROJECT_DIR/venv"

# Runtime files
PID_FILES=(
    "/tmp/yoru-agent-api.pid"
    "/tmp/yoru-agent-web.pid"
)

LOG_FILES=(
    "/tmp/yoru-agent-api.log"
    "/tmp/yoru-agent-web.log"
)

echo "=========================================================="
echo "              UNINSTALL YORU-AGENT                        "
echo "=========================================================="

# 1. Hentikan API dan Dashboard
if [[ -f "$START_SCRIPT" ]]; then
    echo ""
    echo "[1/5] Menghentikan API dan Dashboard..."

    bash "$START_SCRIPT" stop

    echo "[OK] Proses aplikasi telah dihentikan."
else
    echo "[INFO] start-yoru-agent.sh tidak ditemukan. Melewati."
fi

# 2. Hapus file sudoers
echo ""
echo "[2/5] Menghapus konfigurasi sudoers..."

if [[ -f "$SUDOERS_FILE" ]]; then
    rm -f "$SUDOERS_FILE"
    echo "[OK] Konfigurasi sudoers berhasil dihapus."
else
    echo "[INFO] Konfigurasi sudoers tidak ditemukan."
fi

# 3. Hapus virtual environment
echo ""
echo "[3/5] Menghapus virtual environment..."

if [[ -d "$VENV_DIR" ]]; then
    rm -rf -- "$VENV_DIR"
    echo "[OK] Virtual environment berhasil dihapus."
else
    echo "[INFO] Virtual environment tidak ditemukan."
fi

# 4. Hapus akun sistem
echo ""
echo "[4/5] Menghapus akun sistem..."

if id "$TARGET_USER" &>/dev/null; then
    userdel -r "$TARGET_USER"
    echo "[OK] Akun sistem $TARGET_USER berhasil dihapus."
else
    echo "[INFO] Akun sistem $TARGET_USER tidak ditemukan."
fi

# 5. Bersihkan file runtime
echo ""
echo "[5/5] Membersihkan file runtime..."

for file in "${PID_FILES[@]}" "${LOG_FILES[@]}"; do
    if [[ -f "$file" ]]; then
        rm -f -- "$file"
    fi
done

echo "[OK] File runtime berhasil dibersihkan."

echo ""
echo "=========================================================="
echo "          UNINSTALL YORU-AGENT SELESAI                    "
echo "=========================================================="
echo ""
echo "Direktori proyek masih tersedia:"
echo "$PROJECT_DIR"
echo ""
echo "Anda sekarang dapat menghapus direktori proyek jika sudah tidak diperlukan."
echo ""