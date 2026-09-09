#!/bin/bash
# audit.sh - Audit SSH Login Grace Time & Max Auth Tries (CIS 5.1.13 & 5.1.16)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$(dirname "$SCRIPT_DIR")/logs"
LOG_FILE="$LOG_DIR/audit.json"
SSHD_CONFIG="/etc/ssh/sshd_config"

mkdir -p "$LOG_DIR"

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

# Mendapatkan parameter sshd aktif (menggunakan sshd -T jika ada, fallback ke grep)
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

log_json "INFO" "audit_start" "none" "none" "Memulai audit SSH Login Limits (CIS 5.1.13 & 5.1.16)"

# ------------------------------------------------------------------------------
# AUDIT CIS 5.1.13: LoginGraceTime (<= 60s)
# ------------------------------------------------------------------------------
LOGIN_GRACE_TIME=$(get_sshd_param "logingracetime")

if [ -z "$LOGIN_GRACE_TIME" ]; then
    log_json "WARNING" "audit_result" "5.1.13" "not_set" "LoginGraceTime tidak diatur secara eksplisit (Default: 120s)"
else
    # Ekstrak nilai dalam detik jika memakai akhiran 'm' atau 's'
    if [[ "$LOGIN_GRACE_TIME" =~ ([0-9]+)m ]]; then
        VAL_GRACE=$(( ${BASH_REMATCH[1]} * 60 ))
    elif [[ "$LOGIN_GRACE_TIME" =~ ([0-9]+)s? ]]; then
        VAL_GRACE=${BASH_REMATCH[1]}
    else
        VAL_GRACE=999
    fi

    if [ "$VAL_GRACE" -gt 0 ] && [ "$VAL_GRACE" -le 60 ]; then
        log_json "INFO" "audit_result" "5.1.13" "$LOGIN_GRACE_TIME" "LoginGraceTime AMAN / Sesuai CIS (Status: $LOGIN_GRACE_TIME)"
    else
        log_json "WARNING" "audit_result" "5.1.13" "$LOGIN_GRACE_TIME" "LoginGraceTime di atas 60 detik (Status: $LOGIN_GRACE_TIME)"
    fi
fi

# ------------------------------------------------------------------------------
# AUDIT CIS 5.1.16: MaxAuthTries (<= 4)
# ------------------------------------------------------------------------------
MAX_AUTH_TRIES=$(get_sshd_param "maxauthtries")

if [ -z "$MAX_AUTH_TRIES" ]; then
    log_json "WARNING" "audit_result" "5.1.16" "not_set" "MaxAuthTries tidak diatur secara eksplisit (Default: 6)"
else
    if [[ "$MAX_AUTH_TRIES" =~ ^[0-9]+$ ]] && [ "$MAX_AUTH_TRIES" -le 4 ] && [ "$MAX_AUTH_TRIES" -gt 0 ]; then
        log_json "INFO" "audit_result" "5.1.16" "$MAX_AUTH_TRIES" "MaxAuthTries AMAN / Sesuai CIS (Status: $MAX_AUTH_TRIES)"
    else
        log_json "WARNING" "audit_result" "5.1.16" "$MAX_AUTH_TRIES" "MaxAuthTries di atas 4 (Status: $MAX_AUTH_TRIES)"
    fi
fi

log_json "INFO" "audit_end" "none" "none" "Audit selesai"
