#!/usr/bin/env bash

set -Eeuo pipefail

# Project configuration
PROJECT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$PROJECT_DIR/venv"
PYTHON="$VENV_DIR/bin/python"

# Process files
API_PID="/tmp/yoru-agent-api.pid"
WEB_PID="/tmp/yoru-agent-web.pid"

# Runtime logs (not stored in the project)
API_LOG="/tmp/yoru-agent-api.log"
WEB_LOG="/tmp/yoru-agent-web.log"

# Check process using PID and command
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

# Main commands
case "${1:-start}" in
    start)
        check_environment

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
            --server.address 0.0.0.0 \
            --server.port 8501
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