#!/bin/bash

# Pastikan script dijalankan sebagai root
if [ "$EUID" -ne 0 ]; then
  echo "[-] Jalankan skrip ini menggunakan sudo atau sebagai root!"
  exit 1
fi

TARGET_USER="yoru-agent"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATE_FILE="$PROJECT_DIR/setup/yoru-agent.sudoers"
TARGET_FILE="/etc/sudoers.d/yoru-agent"

echo "[+] Memulai penyiapan lingkungan untuk Yoru-Agent..."

# 1. Buat system user 'yoru-agent' jika belum ada
if id "$TARGET_USER" &>/dev/null; then
  echo "[i] User sistem '$TARGET_USER' sudah ada. Melewati pembuatan user."
else
  echo "[+] Membuat system user baru: $TARGET_USER..."
  useradd -r -s /bin/bash -m -d /home/$TARGET_USER $TARGET_USER
  echo "[+] User '$TARGET_USER' berhasil dibuat."
fi

# 2. Atur kepemilikan (ownership) folder proyek agar dapat diakses oleh user yoru-agent
echo "[+] Mengatur kepemilikan folder proyek ke $TARGET_USER..."
chown -R $TARGET_USER:$TARGET_USER "$PROJECT_DIR"

# Pastikan folder logs dan tmp memiliki izin baca-tulis penuh untuk user terkait
mkdir -p "$PROJECT_DIR/logs"
chmod -R 775 "$PROJECT_DIR/logs"

# 3. Konfigurasi file Sudoers
echo "[+] Menyiapkan konfigurasi sudoers untuk $TARGET_USER..."
if [ ! -f "$TEMPLATE_FILE" ]; then
  echo "[-] Error: File template sudoers tidak ditemukan di $TEMPLATE_FILE"
  exit 1
fi

# Mengganti path placeholder /opt/yoru-agent dengan path asli proyek secara dinamis
sed "s|/opt/yoru-agent|$PROJECT_DIR|g" "$TEMPLATE_FILE" > "$TARGET_FILE"

# Atur perizinan file sudoers ke 440 (wajib agar dibaca oleh sudo)
chmod 440 "$TARGET_FILE"

# 4. Validasi sintaks sudoers
if visudo -c -f "$TARGET_FILE"; then
  echo "[+] Berhasil! Lingkungan dan konfigurasi sudoers untuk Yoru-Agent telah terpasang dengan aman."
  echo "[+] Direktori proyek terdaftar di: $PROJECT_DIR"
else
  echo "[-] Peringatan: Terdapat kesalahan sintaks pada file sudoers!"
  rm -f "$TARGET_FILE"
  exit 1
fi