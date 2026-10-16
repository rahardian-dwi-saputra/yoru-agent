#!/bin/bash

# Pastikan script dijalankan sebagai root
if [ "$EUID" -ne 0 ]; then
  echo "[-] Jalankan skrip ini menggunakan sudo atau sebagai root!"
  exit 1
fi

TARGET_USER="yoru-agent"
PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SUDOERS_FILE="/etc/sudoers.d/yoru-agent"

echo "[+] Memulai proses pencopotan (uninstall) Yoru-Agent..."

# 1. Hapus file konfigurasi sudoers
if [ -f "$SUDOERS_FILE" ]; then
  echo "[+] Menghapus konfigurasi sudoers: $SUDOERS_FILE..."
  rm -f "$SUDOERS_FILE"
  echo "[+] File sudoers berhasil dihapus."
else
  echo "[i] File sudoers untuk $TARGET_USER tidak ditemukan. Melewati."
fi

# 2. Hapus virtual environment jika ada di dalam direktori proyek
VENV_DIR="$PROJECT_DIR/venv"
if [ -d "$VENV_DIR" ]; then
  echo "[+] Menghapus virtual environment di: $VENV_DIR..."
  rm -rf "$VENV_DIR"
  echo "[+] Virtual environment berhasil dihapus."
fi

# 3. Hapus system user 'yoru-agent' beserta home directory-nya (opsional)
if id "$TARGET_USER" &>/dev/null; then
  echo "[+] Menghapus system user '$TARGET_USER'..."
  # Menggunakan userdel dengan opsi -r untuk menghapus home directory (/home/yoru-agent)
  userdel -r "$TARGET_USER" 2>/dev/null || userdel "$TARGET_USER"
  echo "[+] User '$TARGET_USER' berhasil dihapus."
else
  echo "[i] User sistem '$TARGET_USER' tidak ditemukan. Melewati."
fi

# 4. Kembalikan kepemilikan folder proyek ke user utama/normal (opsional, agar bisa diakses kembali secara penuh)
# Mendapatkan user non-root terakhir yang memanggil sudo jika tersedia, atau membiarkannya
if [ -n "$SUDO_USER" ]; then
  echo "[+] Mengembalikan kepemilikan folder proyek ke user asli ($SUDO_USER)..."
  chown -R "$SUDO_USER:$SUDO_USER" "$PROJECT_DIR"
fi

echo ""
echo "[+] Selesai! Yoru-Agent berhasil dicopot dari sistem."
echo "[+] Direktori proyek tetap berada di: $PROJECT_DIR"