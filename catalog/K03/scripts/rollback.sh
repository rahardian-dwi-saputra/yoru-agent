#!/bin/bash
# rollback.sh - Rollback SSH Login Limits to Default Settings (CIS 5.1.13 & 5.1.16)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$(dirname "$SCRIPT_DIR")/logs"
LOG_FILE="$LOG_DIR/rollback.json"
SSHD_CONFIG="/etc/ssh/sshd_config"
LOCK_FILE="/tmp/ssh_rollback_k03.lock"

mkdir -p "$LOG_DIR"

# 1. PENCEGAHAN CONCURRENCY / CRASH DENGAN LOCK FILE
exec 200>"$LOCK_FILE"
if ! flock -n 200; then
    echo "[ERROR] Script rollback lain sedang berjalan. Batalkan eksekusi."
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

log_json "INFO" "rollback_start" "none" "none" "Memulai rollback SSH Login Limits (CIS 5.1.13 & 5.1.16)"

# Membaca nilai aktif saat ini
CURR_GRACE=$(get_sshd_param "logingracetime")
CURR_TRIES=$(get_sshd_param "maxauthtries")

# Normalisasi nilai LoginGraceTime ke detik
VAL_GRACE=120
if [[ "$CURR_GRACE" =~ ([0-9]+)m ]]; then
    VAL_GRACE=$(( ${BASH_REMATCH[1]} * 60 ))
elif [[ "$CURR_GRACE" =~ ([0-9]+)s? ]]; then
    VAL_GRACE=${BASH_REMATCH[1]}
elif [ -z "$CURR_GRACE" ]; then
    VAL_GRACE=120
fi

VAL_TRIES=${CURR_TRIES:-6}

# 2. CEK KONDISI PEMBATALAN ROLLBACK
# Jika MaxAuthTries >= 6 DAN LoginGraceTime >= 120 detik (Default Ubuntu/OpenSSH)
if [ "$VAL_TRIES" -ge 6 ] 2>/dev/null && [ "$VAL_GRACE" -ge 120 ]; then
    log_json "INFO" "rollback_skip" "5.1.13,5.1.16" "LoginGraceTime:${VAL_GRACE}s,MaxAuthTries:${VAL_TRIES}" "Konfigurasi sudah bernilai default (MaxAuthTries >= 6 & LoginGraceTime >= 120s). Rollback dibatalkan."
    log_json "INFO" "rollback_end" "none" "none" "Rollback selesai (no changes needed)"
    exit 0
fi

# Fungsi helper untuk memperbarui atau menambahkan parameter tunggal
set_sshd_parameter() {
    local PARAM_NAME="$1"
    local TARGET_VAL="$2"

    if grep -iqE "^\s*${PARAM_NAME}\s+" "$SSHD_CONFIG"; then
        # Memperbaiki perintah sed agar mengganti seluruh baris dengan parameter dan nilai baru secara akurat
        sed -i -E "s/^\s*${PARAM_NAME}\s+.*/${PARAM_NAME} ${TARGET_VAL}/i" "$SSHD_CONFIG"
    else
        # Jika belum ada, tambahkan di akhir file
        echo "${PARAM_NAME} ${TARGET_VAL}" >> "$SSHD_CONFIG"
    fi
}

# ------------------------------------------------------------------------------
# 3. PENERAPAN ROLLBACK HANYA PADA PARAMETER TERKAIT
# ------------------------------------------------------------------------------
# Backup sshd_config sebelum diubah
BACKUP_FILE="${SSHD_CONFIG}.rollback_bak_$(date +%Y%m%d_%H%M%S)"
cp "$SSHD_CONFIG" "$BACKUP_FILE"
log_json "INFO" "rollback_backup" "none" "none" "Dibuat backup sshd_config di $BACKUP_FILE"

# 1. Mengembalikan LoginGraceTime menjadi 120 (default)
set_sshd_parameter "LoginGraceTime" "120"
log_json "INFO" "rollback_apply" "5.1.13" "120" "Mengembalikan LoginGraceTime ke nilai default 120 detik"

# 2. Mengembalikan MaxAuthTries menjadi 6 (default)
set_sshd_parameter "MaxAuthTries" "6"
log_json "INFO" "rollback_apply" "5.1.16" "6" "Mengembalikan MaxAuthTries ke nilai default 6 kali"

# 4. VALIDASI & RELOAD SERVICE
if sshd -t 2>/dev/null; then
    systemctl reload sshd || service sshd reload
    log_json "INFO" "rollback_success" "5.1.13,5.1.16" "LoginGraceTime:120,MaxAuthTries:6" "Rollback berhasil diterapkan dan SSH service telah di-reload"
else
    # Restore dari backup jika sintaks invalid
    cp "$BACKUP_FILE" "$SSHD_CONFIG"
    log_json "ERROR" "rollback_failed" "5.1.13,5.1.16" "invalid_config" "Sintaks sshd_config tidak valid setelah rollback. Melakukan pemulihan otomatis."
    exit 1
fi

log_json "INFO" "rollback_end" "none" "none" "Rollback selesai"
