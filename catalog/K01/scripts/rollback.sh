#!/bin/bash
# rollback.sh - Memulihkan HANYA konfigurasi PermitRootLogin tanpa menimpa parameter lain

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$(dirname "$SCRIPT_DIR")/logs"
LOG_FILE="$LOG_DIR/rollback.json"
SSHD_CONFIG="/etc/ssh/sshd_config"
LOCK_FILE="/tmp/sshd_config.lock"

mkdir -p "$LOG_DIR"

# Lock file untuk mencegah Race Condition dengan endpoint/skrip lain
exec 200>"$LOCK_FILE"
if ! flock -w 10 200; then
    echo '[ERROR] File sshd_config sedang diakses oleh proses lain.'
    exit 1
fi

log_json() {
    local LEVEL="$1"
    local EVENT="$2"
    local STATUS_CODE="$3"
    local MESSAGE="$4"
    local TIMESTAMP
    TIMESTAMP=$(date -Iseconds)

    echo "[$LEVEL] $MESSAGE"

    printf '{"timestamp":"%s","level":"%s","event":"%s","status_code":"%s","message":"%s"}\n' \
        "$TIMESTAMP" "$LEVEL" "$EVENT" "$STATUS_CODE" "$MESSAGE" >> "$LOG_FILE"
}

log_json "INFO" "rollback_start" "initiated" "Memulai rollback spesifik parameter PermitRootLogin..."

# Cek status saat ini
CURRENT_STATUS=$(grep -i "^PermitRootLogin" $SSHD_CONFIG | awk '{print $2}')

# Nilai target rollback (default SSH biasanya 'yes' atau 'prohibit-password')
TARGET_VALUE="yes"

if [ "$CURRENT_STATUS" == "$TARGET_VALUE" ]; then
    log_json "INFO" "rollback_aborted" "already_target" "Dibatalkan: PermitRootLogin sudah bernilai '$TARGET_VALUE'."
    exit 0
fi

# Buat file temporary untuk Atomic Write (menghindari korupsi data)
TMP_CONFIG=$(mktemp /tmp/sshd_config.XXXXXX)
cp "$SSHD_CONFIG" "$TMP_CONFIG"

# Ubah HANYA baris PermitRootLogin di file temporary
if grep -q -i "^PermitRootLogin" "$TMP_CONFIG"; then
    sed -i "s/^PermitRootLogin.*/PermitRootLogin $TARGET_VALUE/i" "$TMP_CONFIG"
else
    echo "PermitRootLogin $TARGET_VALUE" >> "$TMP_CONFIG"
fi

# Validasi sintaks sebelum menimpa file utama
if sshd -t -f "$TMP_CONFIG"; then
    # Menggantikan file secara atomic
    mv "$TMP_CONFIG" "$SSHD_CONFIG"
    systemctl restart sshd || systemctl restart ssh
    log_json "SUCCESS" "rollback_success" "completed" "PermitRootLogin berhasil dikembalikan ke '$TARGET_VALUE'. Konfigurasi lain tetap terjaga."
else
    rm -f "$TMP_CONFIG"
    log_json "ERROR" "rollback_failed" "invalid_config" "Sintaks konfigurasi invalid! Rollback dibatalkan."
    exit 1
fi

log_json "INFO" "rollback_end" "completed" "Proses rollback selesai."