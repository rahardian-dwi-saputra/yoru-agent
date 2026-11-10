#!/bin/bash

set -Eeuo pipefail

# ==========================================================
# YORU-AGENT ENVIRONMENT INSTALLATION
# ==========================================================


# 1. Pastikan script dijalankan sebagai root
if [[ "$EUID" -ne 0 ]]; then
    echo "[-] Jalankan skrip menggunakan sudo atau sebagai root!"
    exit 1
fi

# 2. Konfigurasi Direktori
TARGET_USER="yoru-agent"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

TEMPLATE_FILE="$PROJECT_DIR/setup/yoru-agent.sudoers"
TARGET_FILE="/etc/sudoers.d/yoru-agent"
TEMP_FILE="$(mktemp /etc/sudoers.d/yoru-agent.XXXXXX)"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

cleanup() {
    rm -f "$TEMP_FILE"
}

trap cleanup EXIT

echo -e "${GREEN}[+] Memulai penyiapan lingkungan Yoru-Agent...${NC}"


# 3. Pemeriksaan Dependencies
if ! command -v curl &>/dev/null; then
    echo -e "${YELLOW}[*] Menginstall curl...${NC}"
    apt-get update
    apt-get install -y curl
fi

# 4. Instalasi Taskfile CLI
if ! command -v task &>/dev/null; then
    echo -e "${GREEN}[*] Menginstall Taskfile CLI...${NC}"

    sh -c "$(curl --fail --silent --show-error --location https://taskfile.dev/install.sh)" -- -d -b /usr/local/bin

    if ! command -v task &>/dev/null; then
        echo -e "${RED}[-] Instalasi Taskfile CLI gagal.${NC}"
        exit 1
    fi

    echo -e "${GREEN}[OK] Taskfile CLI berhasil diinstall.${NC}"
else
    echo -e "${GREEN}[OK] Taskfile CLI sudah terinstall.${NC}"
fi

# 5. Pembuatan System User
if id "$TARGET_USER" &>/dev/null; then
    echo -e "${YELLOW}[i] User '$TARGET_USER' sudah tersedia.${NC}"
else
    echo -e "${GREEN}[+] Membuat system user '$TARGET_USER'...${NC}"

    useradd \
        --system \
        --create-home \
        --home-dir "/home/$TARGET_USER" \
        --shell /bin/bash \
        "$TARGET_USER"

    echo -e "${GREEN}[OK] User berhasil dibuat.${NC}"
fi


# 6. PENGATURAN OWNERSHIP DAN PERMISSION

echo -e "${GREEN}[+] Mengatur permission direktori proyek...${NC}"

# Source code tetap dimiliki root agar tidak dapat dimodifikasi
# oleh user aplikasi yang memiliki akses sudo.

chown root:root "$PROJECT_DIR"
chmod 755 "$PROJECT_DIR"

echo -e "${GREEN}[OK] Permission direktori berhasil dikonfigurasi.${NC}"

# 7. SSH Privilege Separtion Directory
echo -e "${GREEN}[+] Menyiapkan direktori privilege separation SSH...${NC}"

install -d -o root -g root -m 0755 /run/sshd

echo -e "${GREEN}[OK] Direktori /run/sshd berhasil disiapkan.${NC}"


# 8. Konfigurasi Sudoers
echo -e "${GREEN}[+] Menyiapkan konfigurasi sudoers...${NC}"

if [[ ! -f "$TEMPLATE_FILE" ]]; then
    echo -e "${RED}[-] Template sudoers tidak ditemukan: $TEMPLATE_FILE${NC}"
    exit 1
fi

# Mengganti placeholder path proyek dan membersihkan CRLF.

sed "s|/opt/yoru-agent|$PROJECT_DIR|g" "$TEMPLATE_FILE" \
    | tr -d '\r' > "$TEMP_FILE"

# Mengatur ownership dan permission.

chown root:root "$TEMP_FILE"
chmod 0440 "$TEMP_FILE"

# Validasi sebelum memasang konfigurasi.

if visudo -cf "$TEMP_FILE"; then
    mv -f "$TEMP_FILE" "$TARGET_FILE"
    chown root:root "$TARGET_FILE"
    chmod 0440 "$TARGET_FILE"

    echo -e "${GREEN}[OK] Konfigurasi sudoers berhasil dipasang.${NC}"
else
    echo -e "${RED}[-] Kesalahan sintaks pada konfigurasi sudoers!${NC}"
    exit 1
fi

# 9. Validasi akhir
echo -e "${GREEN}[+] Memvalidasi instalasi...${NC}"

if ! visudo -c; then
    echo -e "${RED}[-] Validasi konfigurasi sudoers sistem gagal.${NC}"
    exit 1
fi

echo
echo -e "${GREEN}==========================================================${NC}"
echo -e "${GREEN}[OK] INSTALASI LINGKUNGAN YORU-AGENT SELESAI${NC}"
echo -e "${GREEN}==========================================================${NC}"

echo "[i] Project Directory : $PROJECT_DIR"
echo "[i] Application User  : $TARGET_USER"
echo "[i] Taskfile CLI      : $(command -v task)"
echo "[i] SSH Directory     : /run/sshd"
echo "[i] Sudoers           : $TARGET_FILE"