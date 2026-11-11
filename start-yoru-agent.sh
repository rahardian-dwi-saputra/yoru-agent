#!/usr/bin/env bash

set -Eeuo pipefail

# Project configuration
PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_DIR/venv"
PYTHON="$VENV_DIR/bin/python"

# Process files
API_PID="/tmp/yoru-agent-api.pid"
WEB_PID="/tmp/yoru-agent-web.pid"

# Runtime logs
API_LOG="/tmp/yoru-agent-api.log"
WEB_LOG="/tmp/yoru-agent-web.log"


# Check whether a service is running
is_running() {
    local pid_file="$1"
    local process_name="$2"

    [[ -f "$pid_file" ]] || return 1

    local pid
    pid="$(cat "$pid_file")"

    kill -0 "$pid" 2>/dev/null || return 1

    ps -p "$pid" -o args= | grep -Fq "$process_name"
}


# Start service
start_service() {
    local name="$1"
    local pid_file="$2"
    local log_file="$3"
    local process_name="$4"
    shift 4

    if is_running "$pid_file" "$process_name"; then
        echo "[OK] $name sudah berjalan."
        return 0
    fi

    rm -f "$pid_file"

    echo "[*] Menjalankan $name..."

    nohup "$@" > "$log_file" 2>&1 &
    local pid=$!

    echo "$pid" > "$pid_file"

    sleep 2

    if is_running "$pid_file" "$process_name"; then
        echo "[OK] $name berhasil dijalankan (PID: $pid)."
    else
        rm -f "$pid_file"
        echo "[ERROR] $name gagal dijalankan."
        echo "Periksa log: $log_file"
        return 1
    fi
}


# Stop service
stop_service() {
    local name="$1"
    local pid_file="$2"
    local process_name="$3"

    if ! is_running "$pid_file" "$process_name"; then
        rm -f "$pid_file"
        echo "[INFO] $name tidak sedang berjalan."
        return 0
    fi

    local pid
    pid="$(cat "$pid_file")"

    echo "[*] Menghentikan $name..."

    kill "$pid"

    for _ in {1..10}; do
        if ! kill -0 "$pid" 2>/dev/null; then
            break
        fi
        sleep 1
    done

    if kill -0 "$pid" 2>/dev/null; then
        kill -9 "$pid" 2>/dev/null || true
    fi

    rm -f "$pid_file"

    echo "[OK] $name berhasil dihentikan."
}


# Show service status
show_status() {
    local name="$1"
    local pid_file="$2"
    local process_name="$3"

    if is_running "$pid_file" "$process_name"; then
        echo "[RUNNING] $name (PID: $(cat "$pid_file"))"
    else
        echo "[STOPPED] $name"
    fi
}


# Validate environment
check_environment() {
    if [[ ! -x "$PYTHON" ]]; then
        echo "[ERROR] Virtual environment tidak ditemukan: $VENV_DIR"
        exit 1
    fi

    if [[ ! -f "$PROJECT_DIR/api/main.py" ]]; then
        echo "[ERROR] File api/main.py tidak ditemukan."
        exit 1
    fi

    if [[ ! -f "$PROJECT_DIR/web/app.py" ]]; then
        echo "[ERROR] File web/app.py tidak ditemukan."
        exit 1
    fi
}


# Load application configuration
load_app_config() {
    local config

    if ! config="$(
        PROJECT_DIR="$PROJECT_DIR" "$PYTHON" -c '
import os
import sys

sys.path.insert(0, os.environ["PROJECT_DIR"])

from config.api import API_HOST, API_PORT
from config.web import WEB_HOST, WEB_PORT

print(API_HOST)
print(API_PORT)
print(WEB_HOST)
print(WEB_PORT)
'
    )"; then
        echo "[ERROR] Gagal membaca konfigurasi aplikasi."
        exit 1
    fi

    mapfile -t APP_CONFIG <<< "$config"

    if [[ "${#APP_CONFIG[@]}" -ne 4 ]]; then
        echo "[ERROR] Konfigurasi host dan port tidak lengkap."
        exit 1
    fi

    API_HOST="${APP_CONFIG[0]}"
    API_PORT="${APP_CONFIG[1]}"
    WEB_HOST="${APP_CONFIG[2]}"
    WEB_PORT="${APP_CONFIG[3]}"

    if [[ -z "$API_HOST" || -z "$WEB_HOST" ]]; then
        echo "[ERROR] Konfigurasi host tidak boleh kosong."
        exit 1
    fi

    if [[ ! "$API_PORT" =~ ^[0-9]+$ ]] ||
       [[ ! "$WEB_PORT" =~ ^[0-9]+$ ]]; then
        echo "[ERROR] Konfigurasi port harus berupa angka."
        exit 1
    fi

    # Normalize port values to avoid Bash octal interpretation.
    API_PORT=$((10#$API_PORT))
    WEB_PORT=$((10#$WEB_PORT))

    if (( API_PORT < 1 || API_PORT > 65535 )) ||
       (( WEB_PORT < 1 || WEB_PORT > 65535 )); then
        echo "[ERROR] Port harus berada dalam rentang 1-65535."
        exit 1
    fi
}


# Resolve address for browser access
get_access_host() {
    local host="$1"
    local address

    case "$host" in
        0.0.0.0)
            address="$(hostname -I 2>/dev/null | awk '{print $1}')"
            echo "${address:-localhost}"
            ;;
        ::)
            echo "localhost"
            ;;
        *)
            echo "$host"
            ;;
    esac
}


# Show application access information
show_access_info() {
    local api_access_host
    local web_access_host

    api_access_host="$(get_access_host "$API_HOST")"
    web_access_host="$(get_access_host "$WEB_HOST")"

    echo ""
    echo "=========================================================="
    echo "             YORU-AGENT ACCESS INFORMATION"
    echo "=========================================================="
    echo ""
    echo "API Backend"
    echo "  Bind Address : $API_HOST"
    echo "  Port         : $API_PORT"
    echo "  API URL      : http://${api_access_host}:${API_PORT}"
    echo "  Swagger UI   : http://${api_access_host}:${API_PORT}/docs"
    echo ""
    echo "Web Dashboard"
    echo "  Bind Address : $WEB_HOST"
    echo "  Port         : $WEB_PORT"
    echo "  URL          : http://${web_access_host}:${WEB_PORT}"
    echo ""
    echo "Runtime Logs"
    echo "  API          : $API_LOG"
    echo "  Web          : $WEB_LOG"
    echo ""
    echo "=========================================================="
}


# Main commands
case "${1:-start}" in
    start)
        check_environment
        load_app_config

        cd "$PROJECT_DIR"

        start_service \
            "FastAPI" \
            "$API_PID" \
            "$API_LOG" \
            "api/main.py" \
            "$PYTHON" "$PROJECT_DIR/api/main.py"

        start_service \
            "Web Dashboard" \
            "$WEB_PID" \
            "$WEB_LOG" \
            "web/app.py" \
            "$PYTHON" -m streamlit run "$PROJECT_DIR/web/app.py" \
            --server.address "$WEB_HOST" \
            --server.port "$WEB_PORT" \
            --server.headless true \
            --browser.gatherUsageStats false

        show_access_info
        ;;

    stop)
        stop_service "Web Dashboard" "$WEB_PID" "web/app.py"
        stop_service "FastAPI" "$API_PID" "api/main.py"
        ;;

    restart)
        "$0" stop
        "$0" start
        ;;

    status)
        show_status "FastAPI" "$API_PID" "api/main.py"
        show_status "Web Dashboard" "$WEB_PID" "web/app.py"
        ;;

    *)
        echo "Penggunaan: $0 {start|stop|restart|status}"
        exit 1
        ;;
esac
