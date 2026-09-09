#!/bin/bash
# hardening.sh - SSH Hardening Login Limits (CIS 5.1.13 & 5.1.16)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$(dirname "$SCRIPT_DIR")/logs"
LOG_FILE="$LOG_DIR/hardening.json"
SSHD_CONFIG="/etc/ssh/sshd_config"
LOCK_FILE="/tmp/ssh_hardening_k03.lock"

mkdir -p "$LOG_DIR"

# 1. PENCEGAHAN CONCURRENCY / CRASH DENGAN LOCK FILE
exec 200>"$LOCK_FILE"
if ! flock -n 200; then
    echo "[ERROR] Script hardening lain sedang berjalan. Batalkan eksekusi."
    exit 1
fi

# Fungsi mencatat log dalam format JSON murni
log_json() {
    local LEVEL="$1"
    local EVENT="$2"
    local CIS_ID="$3"
    local CONFIG_VAL="$4"
    local MESSAGE="$5"
    local TIMESTAMP
    TIMESTAMP=$(date -Iseconds)

    # Menampilkan teks ringkas di terminal
    echo "[$LEVEL] $MESSAGE"

    # Menyimpan baris JSON terstruktur ke file log (JSON Lines)
    printf '{"timestamp":"%s","level":"%s","event":"%s","cis_id":"%s","config_value":"%s","message":"%s"}
' \
        "$TIMESTAMP" "$LEVEL" "$EVENT" "$CIS_ID" "$CONFIG_VAL" "$MESSAGE" >> "$LOG_FILE"
}

# Mendapatkan parameter sshd aktif
get_sshd_param() {
    local param_name="$1"
    local value=""

    if command -v sshd &> /dev/null; then
        value=$(sshd -T 2>/dev/null | grep -i "^${param_name} " | awk '{print $2}')
    fi

    if [ -z "$value" ]; then
        value=$(grep -ihE "^\s*${param_name}\s+" "$SSHD_CONFIG" /etc/ssh/sshd_config.d/*.conf 2>/dev/null | tail -n 1 | awk '{print $2}')
    fi

    echo "$value"
}

log_json "INFO" "hardening_start" "none" "none" "Memulai hardening SSH Login Limits (CIS 5.1.13 & 5.1.16)"

# Membaca nilai aktif saat ini
CURR_GRACE=$(get_sshd_param "logingracetime")
CURR_TRIES=$(get_sshd_param "maxauthtries")

# Normalisasi nilai LoginGraceTime ke detik
VAL_GRACE=999
if [[ "$CURR_GRACE" =~ ([0-9]+)m ]]; then
    VAL_GRACE=$(( ${BASH_REMATCH[1]} * 60 ))
elif [[ "$CURR_GRACE" =~ ([0-9]+)s? ]]; then
    VAL_GRACE=${BASH_REMATCH[1]}
fi

# Cek kondisi pembatalan hardening
# Jika MaxAuthTries <= 3 DAN LoginGraceTime <= 30 detik
if [ "$CURR_TRIES" -le 3 ] 2>/dev/null && [ "$VAL_GRACE" -le 30 ]; then
    log_json "INFO" "hardening_skip" "5.1.13,5.1.16" "LoginGraceTime:${CURR_GRACE},MaxAuthTries:${CURR_TRIES}" "Konfigurasi sudah optimal (MaxAuthTries <= 3 & LoginGraceTime <= 30s). Hardening dibatalkan."
    log_json "INFO" "hardening_end" "none" "none" "Hardening selesai (no changes needed)"
    exit 0
fi

# Fungsi helper untuk memperbarui atau menambahkan parameter tunggal
set_sshd_parameter() {
    local PARAM_NAME="$1"
    local TARGET_VAL="$2"

    if grep -iqE "^\s*${PARAM_NAME}\s+" "$SSHD_CONFIG"; then
        # Mengubah baris parameter yang sudah ada tanpa menyentuh bagian lain
        sed -i -E "s/^\s*(${PARAM_NAME})\s+.*/ ${TARGET_VAL}/i" "$SSHD_CONFIG"
    else
        # Jika belum ada, tambahkan di akhir file
        echo "${PARAM_NAME} ${TARGET_VAL}" >> "$SSHD_CONFIG"
    fi
}

# ------------------------------------------------------------------------------
# PENERAPAN HARDENING HANYA PADA PARAMETER TERKAIT
# ------------------------------------------------------------------------------
# Backup sshd_config sebelum diubah
BACKUP_FILE="${SSHD_CONFIG}.bak_$(date +%Y%m%d_%H%M%S)"
cp "$SSHD_CONFIG" "$BACKUP_FILE"
log_json "INFO" "hardening_backup" "none" "none" "Dibuat backup sshd_config di $BACKUP_FILE"

# 1. Terapkan LoginGraceTime 30
set_sshd_parameter "LoginGraceTime" "30"
log_json "INFO" "hardening_apply" "5.1.13" "30" "Mengubah LoginGraceTime menjadi 30 detik"

# 2. Terapkan MaxAuthTries 3
set_sshd_parameter "MaxAuthTries" "3"
log_json "INFO" "hardening_apply" "5.1.16" "3" "Mengubah MaxAuthTries menjadi 3 kali"

# Validasi sintaks SSHD sebelum merestart service
if sshd -t 2>/dev/null; then
    systemctl reload sshd || service sshd reload
    log_json "INFO" "hardening_success" "5.1.13,5.1.16" "LoginGraceTime:30,MaxAuthTries:3" "Hardening berhasil diterapkan dan SSH service telah di-reload"
else
    # Rollback jika sintaks invalid
    cp "$BACKUP_FILE" "$SSHD_CONFIG"
    log_json "ERROR" "hardening_failed" "5.1.13,5.1.16" "invalid_config" "Sintaks sshd_config tidak valid setelah diubah. Melakukan rollback otomatis."
    exit 1
fi

log_json "INFO" "hardening_end" "none" "none" "Hardening selesai"
