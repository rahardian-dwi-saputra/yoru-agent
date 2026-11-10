#!/bin/bash

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
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$PROJECT_DIR/venv"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}[+] Memulai instalasi dependencies Yoru-Agent...${NC}"

# 3. Validasi user
if ! id "$TARGET_USER" &>/dev/null; then
    echo -e "${RED}[-] User '$TARGET_USER' belum tersedia.${NC}"
    echo "    Jalankan setup-environment.sh terlebih dahulu."
    exit 1
fi

TARGET_GROUP="$(id -gn "$TARGET_USER")"


# 4. Konfigurasi API Key
echo -e "${GREEN}[+] Membaca konfigurasi API Key...${NC}"

API_KEY_PATH="$(
    PROJECT_DIR="$PROJECT_DIR" python3 -c '
import os
import sys

sys.path.insert(0, os.environ["PROJECT_DIR"])

from config.api import API_KEY_PATH

print(API_KEY_PATH)
'
)"

if [[ -z "$API_KEY_PATH" || "$API_KEY_PATH" != /* ]]; then
    echo -e "${RED}[-] API_KEY_PATH tidak valid.${NC}"
    exit 1
fi

API_DIR="$(dirname "$API_KEY_PATH")"

mkdir -p "$API_DIR"


# 5. Membuat Virtual Environment
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


# 6. Instalasi Library Python
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


# 7. Generate API KEY
echo
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

    printf '%s\n' "$GENERATED_KEY" > "$TEMP_KEY"

    chown root:"$TARGET_GROUP" "$TEMP_KEY"
    chmod 0640 "$TEMP_KEY"

    mv -f "$TEMP_KEY" "$API_KEY_PATH"

    echo -e "${GREEN}[OK] API Key berhasil dibuat.${NC}"

fi

# Pastikan user aplikasi dapat membaca API Key.
chown root:"$TARGET_GROUP" "$API_KEY_PATH"
chmod 0640 "$API_KEY_PATH"


# 8. Validasi akhir
echo
echo -e "${GREEN}[+] Memvalidasi instalasi...${NC}"

if ! runuser -u "$TARGET_USER" -- test -r "$API_KEY_PATH"; then
    echo -e "${RED}[-] User '$TARGET_USER' tidak dapat membaca API Key.${NC}"
    exit 1
fi

if [[ ! -x "$PYTHON" ]]; then
    echo -e "${RED}[-] Virtual environment tidak valid.${NC}"
    exit 1
fi

echo
echo -e "${GREEN}==========================================================${NC}"
echo -e "${GREEN}[OK] INSTALASI DEPENDENCIES YORU-AGENT SELESAI${NC}"
echo -e "${GREEN}==========================================================${NC}"

echo "[i] Project Directory : $PROJECT_DIR"
echo "[i] Virtual Env       : $VENV_DIR"
echo "[i] Python            : $PYTHON"
echo "[i] API Key           : $API_KEY_PATH"
echo "[i] Application User  : $TARGET_USER"

echo
echo "Untuk mengaktifkan virtual environment:"
echo "source \"$VENV_DIR/bin/activate\""

echo
echo "Untuk melihat API Key:"
echo "sudo cat \"$API_KEY_PATH\""