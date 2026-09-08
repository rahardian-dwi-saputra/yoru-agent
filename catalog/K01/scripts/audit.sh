#!/bin/bash
# audit.sh - Audit SSH Root Login

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_DIR="$(dirname "$SCRIPT_DIR")/logs"
LOG_FILE="$LOG_DIR/audit.json"
SSHD_CONFIG="/etc/ssh/sshd_config"

mkdir -p "$LOG_DIR"

# Fungsi mencatat log dalam format JSON murni
log_json() {
    local LEVEL="$1"
    local EVENT="$2"
    local PERMIT_STATUS="$3"
    local MESSAGE="$4"
    local TIMESTAMP
    TIMESTAMP=$(date -Iseconds)

    # Menampilkan teks ringkas di terminal
    echo "[$LEVEL] $MESSAGE"

    # Menyimpan baris JSON terstruktur ke file log
    printf '{"timestamp":"%s","level":"%s","event":"%s","permit_root_login":"%s","message":"%s"}\n' \
        "$TIMESTAMP" "$LEVEL" "$EVENT" "$PERMIT_STATUS" "$MESSAGE" >> "$LOG_FILE"
}

log_json "INFO" "audit_start" "unknown" "Memulai audit SSH Root Login pada $SSHD_CONFIG"

# Cek parameter PermitRootLogin
STATUS=$(grep -i "^PermitRootLogin" $SSHD_CONFIG | awk '{print $2}')

if [ -z "$STATUS" ]; then
    log_json "WARNING" "audit_result" "not_set" "PermitRootLogin tidak diatur secara eksplisit di sshd_config"
elif [ "$STATUS" == "yes" ]; then
    log_json "WARNING" "audit_result" "yes" "Root BISA login via SSH (PermitRootLogin yes)"
else
    log_json "INFO" "audit_result" "$STATUS" "Root login SSH AMAN / Dibatasi (Status: $STATUS)"
fi

log_json "INFO" "audit_end" "${STATUS:-not_set}" "Audit selesai"