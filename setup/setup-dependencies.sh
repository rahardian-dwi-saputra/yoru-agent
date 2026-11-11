#!/usr/bin/env bash

set -Eeuo pipefail

# ==========================================================
# YORU-AGENT DEPENDENCIES INSTALLATION
# ==========================================================

# 1. Validasi hak akses root
if [[ "$EUID" -ne 0 ]]; then
    echo "[-] Jalankan skrip menggunakan sudo atau sebagai root!"
    exit 1
fi

# 2. Konfigurasi direktori
TARGET_USER="yoru-agent"
PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$PROJECT_DIR/venv"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}[+] Memulai instalasi dependencies Yoru-Agent...${NC}"

# 3. Validasi user aplikasi
if ! id "$TARGET_USER" &>/dev/null; then
    echo -e "${RED}[-] User '$TARGET_USER' belum tersedia.${NC}"
    echo "    Jalankan setup-environment.sh terlebih dahulu."
    exit 1
fi

TARGET_GROUP="$(id -gn "$TARGET_USER")"

# 4. Membuat virtual environment
echo -e "${GREEN}[+] Memeriksa virtual environment...${NC}"

if [[ ! -x "$VENV_DIR/bin/python" ]]; then
    echo -e "${YELLOW}[*] Membuat virtual environment...${NC}"

    if ! python3 -m venv "$VENV_DIR"; then
        echo -e "${YELLOW}[*] Menginstall python3-venv...${NC}"

        apt-get update
        apt-get install -y python3-venv

        python3 -m venv "$VENV_DIR"
    fi

    echo -e "${GREEN}[OK] Virtual environment berhasil dibuat.${NC}"
else
    echo -e "${GREEN}[OK] Virtual environment sudah tersedia.${NC}"
fi

PYTHON="$VENV_DIR/bin/python"

# 5. Instalasi library Python
echo -e "${GREEN}[+] Menginstall library Python...${NC}"

"$PYTHON" -m pip install --upgrade pip

"$PYTHON" -m pip install \
    fastapi \
    uvicorn \
    pydantic \
    slowapi \
    python-dotenv \
    pyyaml \
    streamlit \
    requests \
    reportlab \
    pandas \
    google-genai

"$PYTHON" -m pip check

echo -e "${GREEN}[OK] Library Python berhasil diinstall.${NC}"


# 6. Pengaturan akses direktori penyimpanan
echo -e "${GREEN}[+] Menyiapkan direktori penyimpanan...${NC}"

STORAGE_PATHS="$(
    PROJECT_DIR="$PROJECT_DIR" "$PYTHON" -c '
import os
import sys

sys.path.insert(0, os.environ["PROJECT_DIR"])

from config.settings import PLANS_DIR
from config.web import WEB_STORAGE_DIR, DATABASE_PATH

print(PLANS_DIR)
print(WEB_STORAGE_DIR)
print(DATABASE_PATH)
'
)"

mapfile -t STORAGE_PATHS_ARRAY <<< "$STORAGE_PATHS"

if [[ "${#STORAGE_PATHS_ARRAY[@]}" -ne 3 ]]; then
    echo -e "${RED}[-] Gagal membaca konfigurasi direktori penyimpanan.${NC}"
    exit 1
fi

PLANS_DIR="${STORAGE_PATHS_ARRAY[0]}"
WEB_STORAGE_DIR="${STORAGE_PATHS_ARRAY[1]}"
DATABASE_PATH="${STORAGE_PATHS_ARRAY[2]}"

# Validasi seluruh lokasi penyimpanan
for path in "$PLANS_DIR" "$WEB_STORAGE_DIR" "$DATABASE_PATH"; do
    if [[ -z "$path" || "$path" != /* ]]; then
        echo -e "${RED}[-] Lokasi penyimpanan tidak valid: $path${NC}"
        exit 1
    fi

    case "$path" in
        "$PROJECT_DIR"/*) ;;
        *)
            echo -e "${RED}[-] Lokasi penyimpanan berada di luar project: $path${NC}"
            exit 1
            ;;
    esac
done

# Siapkan direktori penyimpanan
STORAGE_DIR="$PROJECT_DIR/storage"

mkdir -p "$PLANS_DIR" "$WEB_STORAGE_DIR"

# Atur kepemilikan dan permission direktori
chown "$TARGET_USER:$TARGET_GROUP" \
    "$STORAGE_DIR" \
    "$PLANS_DIR" \
    "$WEB_STORAGE_DIR"

chmod 750 \
    "$STORAGE_DIR" \
    "$PLANS_DIR" \
    "$WEB_STORAGE_DIR"

# Pastikan seluruh file plan dapat dikelola aplikasi
chown -R "$TARGET_USER:$TARGET_GROUP" "$PLANS_DIR"

# Buat database jika belum tersedia
if [[ ! -e "$DATABASE_PATH" ]]; then
    install -o "$TARGET_USER" -g "$TARGET_GROUP" -m 640 \
        /dev/null "$DATABASE_PATH"
else
    if [[ ! -f "$DATABASE_PATH" ]]; then
        echo -e "${RED}[-] Lokasi database bukan file reguler: $DATABASE_PATH${NC}"
        exit 1
    fi

    chown "$TARGET_USER:$TARGET_GROUP" "$DATABASE_PATH"
    chmod 640 "$DATABASE_PATH"
fi

echo -e "${GREEN}[OK] Direktori penyimpanan berhasil disiapkan.${NC}"
echo "[i] Plans Directory    : $PLANS_DIR"
echo "[i] Web Storage        : $WEB_STORAGE_DIR"
echo "[i] Database           : $DATABASE_PATH"


# 7. Membaca konfigurasi API Key
echo -e "${GREEN}[+] Membaca konfigurasi API Key...${NC}"

API_KEY_PATH="$(
    PROJECT_DIR="$PROJECT_DIR" "$PYTHON" -c '
import os
import sys

sys.path.insert(0, os.environ["PROJECT_DIR"])

from config.api import API_KEY_PATH

print(API_KEY_PATH)
'
)"

if [[ -z "$API_KEY_PATH" || "$API_KEY_PATH" != /* ]]; then
    echo -e "${RED}[-] API_KEY_PATH tidak valid atau bukan absolute path.${NC}"
    exit 1
fi

API_DIR="$(dirname "$API_KEY_PATH")"

mkdir -p "$API_DIR"

# 8. Generate API Key
echo -e "${GREEN}[+] Memeriksa API Key...${NC}"

if [[ -f "$API_KEY_PATH" ]]; then

    if [[ ! -s "$API_KEY_PATH" ]]; then
        echo -e "${RED}[-] File API Key ditemukan tetapi kosong.${NC}"
        exit 1
    fi

    echo -e "${GREEN}[OK] API Key sudah tersedia.${NC}"

else

    echo -e "${YELLOW}[*] Menggenerate API Key baru...${NC}"

    if command -v openssl &>/dev/null; then
        GENERATED_KEY="$(openssl rand -hex 32)"
    else
        GENERATED_KEY="$("$PYTHON" -c 'import secrets; print(secrets.token_hex(32))')"
    fi

    TEMP_KEY="$(mktemp "$API_DIR/.api-key.XXXXXX")"

    trap 'rm -f "${TEMP_KEY:-}"' EXIT

    printf '%s\n' "$GENERATED_KEY" > "$TEMP_KEY"

    chown root:"$TARGET_GROUP" "$TEMP_KEY"
    chmod 0640 "$TEMP_KEY"

    mv -f "$TEMP_KEY" "$API_KEY_PATH"

    trap - EXIT

    echo -e "${GREEN}[OK] API Key berhasil dibuat.${NC}"
fi

# Pastikan user aplikasi dapat membaca API Key
chown root:"$TARGET_GROUP" "$API_KEY_PATH"
chmod 0640 "$API_KEY_PATH"

# 9. Validasi akhir
echo -e "${GREEN}[+] Memvalidasi instalasi...${NC}"

if ! runuser -u "$TARGET_USER" -- test -r "$API_KEY_PATH"; then
    echo -e "${RED}[-] User '$TARGET_USER' tidak dapat membaca API Key.${NC}"
    echo "    Periksa izin direktori: $API_DIR"
    exit 1
fi

if [[ ! -x "$PYTHON" ]]; then
    echo -e "${RED}[-] Virtual environment tidak valid.${NC}"
    exit 1
fi

if ! "$PYTHON" -c "import dotenv, fastapi, uvicorn, streamlit"; then
    echo -e "${RED}[-] Validasi library Python gagal.${NC}"
    exit 1
fi

echo ""
echo -e "${GREEN}==========================================================${NC}"
echo -e "${GREEN}[OK] INSTALASI DEPENDENCIES YORU-AGENT SELESAI${NC}"
echo -e "${GREEN}==========================================================${NC}"

echo "[i] Project Directory : $PROJECT_DIR"
echo "[i] Virtual Env       : $VENV_DIR"
echo "[i] Python            : $PYTHON"
echo "[i] API Key           : $API_KEY_PATH"
echo "[i] Application User  : $TARGET_USER"

echo ""
echo "Untuk mengaktifkan virtual environment:"
echo "source \"$VENV_DIR/bin/activate\""

echo ""
echo "Untuk melihat API Key:"
echo "sudo cat \"$API_KEY_PATH\""