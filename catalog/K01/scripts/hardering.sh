#!/bin/bash
# hardening.sh - Menonaktifkan Root Login via SSH

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$(dirname "$SCRIPT_DIR")/logs"
LOG_FILE="$LOG_DIR/hardening.json"
SSHD_CONFIG="/etc/ssh/sshd_config"
LOCK_FILE="/tmp/sshd_config.lock"

mkdir -p "$LOG_DIR"

# Mencegah bentrokan eksekusi dengan endpoint/skrip lain
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

log_json "INFO" "hardening_start" "initiated" "Memulai proses hardening SSH..."

# Cek A: Apakah Root sudah disabled?
CURRENT_ROOT_STATUS=$(grep -i "^PermitRootLogin" $SSHD_CONFIG | awk '{print $2}')
if [ "$CURRENT_ROOT_STATUS" == "no" ]; then
    log_json "INFO" "hardening_aborted" "already_disabled" "Dibatalkan: Root login SSH sudah dalam keadaan nonaktif (PermitRootLogin no)."
    exit 0
fi

# Cek B: Apakah ada user non-root lain yang bisa login?
OTHER_USERS_COUNT=$(awk -F':' '$3 >= 1000 && $7 !~ /(nologin|false)/ {print $1}' /etc/passwd | wc -l)
if [ "$OTHER_USERS_COUNT" -eq 0 ]; then
    log_json "ERROR" "hardening_aborted" "no_other_users" "Dibatalkan demi keamanan: Tidak ditemukan user non-root dengan akses shell!"
    exit 1
fi

log_json "INFO" "safety_check_passed" "ok" "Verifikasi berhasil: Ditemukan $OTHER_USERS_COUNT user non-root."

# Buat file sementara
TMP_CONFIG=$(mktemp /tmp/sshd_config.XXXXXX)
cp "$SSHD_CONFIG" "$TMP_CONFIG"

# Ubah HANYA parameter PermitRootLogin di file sementara
if grep -q -i "^PermitRootLogin" "$TMP_CONFIG"; then
    sed -i 's/^PermitRootLogin.*/PermitRootLogin no/i' "$TMP_CONFIG"
else
    echo "PermitRootLogin no" >> "$TMP_CONFIG"
fi

# Validasi sintaks file sementara sebelum diterapkan ke sistem
if sshd -t -f "$TMP_CONFIG"; then
    # Timpa file utama secara atomic ('mv' bersifat atomic di Linux)
    mv "$TMP_CONFIG" "$SSHD_CONFIG"
    systemctl restart sshd || systemctl restart ssh
    log_json "SUCCESS" "hardening_success" "completed" "Root login via SSH berhasil DINONAKTIFKAN. Parameter lain tetap terjaga."
else
    rm -f "$TMP_CONFIG"
    log_json "ERROR" "hardening_failed" "invalid_config" "Sintaks konfigurasi invalid! Hardening dibatalkan."
    exit 1
fi

log_json "INFO" "hardening_end" "completed" "Proses hardening selesai."