#!/bin/bash
# setup_hermes_agent.sh - Skrip Otomasi Konfigurasi Environment Hermes Agent

set -e

GREEN='\033[0;32m'
NC='\033[0m'
RED='\033[0;31m'

echo -e "${GREEN}[*] Memulai Setup Environment Hermes Agent...${NC}"

# 1. PASTIkan SKRIP DIJALANKAN SEBAGAI ROOT / SUDO
if [ "$EUID" -ne 0 ]; then
  echo -e "${RED}[ERROR] Skrip ini harus dijalankan dengan sudo atau sebagai root.${NC}"
  exit 1
fi

# ==========================================
# 2. OTOMASI PEMBUATAN USER 'yoru-agent'
# ==========================================
TARGET_USER="yoru-agent"

if ! id "$TARGET_USER" &>/dev/null; then
    echo -e "${GREEN}[*] Membuat user sistem baru: ${TARGET_USER}...${NC}"
    # Membuat user dengan home directory dan shell bash
    useradd -m -s /bin/bash "$TARGET_USER"
    # Menambahkan ke grup sudo
    usermod -aG sudo "$TARGET_USER" 2>/dev/null || usermod -aG wheel "$TARGET_USER" 2>/dev/null
    echo -e "${GREEN}[OK] User ${TARGET_USER} berhasil dibuat.${NC}"
else
    echo -e "${GREEN}[OK] User ${TARGET_USER} sudah ada di sistem.${NC}"
fi

# Dapatkan home directory resmi dari target user
USER_HOME=$(getent passwd "$TARGET_USER" | cut -d: -f6)
echo -e "${GREEN}[*] Target User System: ${TARGET_USER} (Home: ${USER_HOME})${NC}"

# ==========================================
# 3. INSTALASI TASKFILE CLI (Task Runner)
# ==========================================
if ! command -v task &> /dev/null; then
    echo -e "${GREEN}[*] Menginstall Taskfile CLI...${NC}"
    sh -c "$(curl --location https://taskfile.dev/install.sh)" -- -d -b /usr/local/bin
    echo -e "${GREEN}[OK] Taskfile CLI berhasil diinstall.${NC}"
else
    echo -e "${GREEN}[OK] Taskfile CLI sudah terinstall.${NC}"
fi

# ==========================================
# 4. KONFIGURASI SUDOERS AKSES PENUH (NOPASSWD)
# ==========================================
SUDOERS_FILE="/etc/sudoers.d/hermes_agent_${TARGET_USER}"

echo -e "${GREEN}[*] Mengonfigurasi izin Sudoers NOPASSWD ALL untuk user ${TARGET_USER}...${NC}"
cat <<EOF > "$SUDOERS_FILE"
# Akses penuh tanpa password untuk eksekusi otomasi Hermes Agent & Taskfile
${TARGET_USER} ALL=(ALL:ALL) NOPASSWD: ALL
EOF

chmod 0440 "$SUDOERS_FILE"

# Validasi sintaks sudoers dengan visudo untuk mencegah lockout
if visudo -cf "$SUDOERS_FILE" &>/dev/null; then
    echo -e "${GREEN}[OK] Konfigurasi sudoers valid dan tersimpan di $SUDOERS_FILE${NC}"
else
    echo -e "${RED}[ERROR] Konfigurasi sudoers invalid! Menghapus file...${NC}"
    rm -f "$SUDOERS_FILE"
    exit 1
fi

# ==========================================
# 5. MEMBUAT FILE PROMPT SYSTEM INSTRUCTION
# ==========================================
HERMES_CONFIG_DIR="${USER_HOME}/.config/hermes-agent"
mkdir -p "$HERMES_CONFIG_DIR"

echo -e "${GREEN}[*] Membuat file System Prompt Hermes Agent...${NC}"
cat <<'EOF' > "${HERMES_CONFIG_DIR}/system_instruction.txt"
[HERMES AGENT SYSTEM INSTRUCTION]
Role: Security Orchestrator for SSH Hardening System

Protocol:
1. Intent Classification & Routing:
   Analyze user input to decide the target module/endpoint:
   - Target Endpoint: http://127.0.0.1:8000/K01
     Use when the user intent relates to SSH Root Access / Login rules (e.g., "amankan root", "matikan root login", "audit root ssh", "rollback root").
   - Target Endpoint: http://127.0.0.1:8000/K03
     Use when the user intent relates to SSH Login Attempt Limits & Timeout rules (e.g., "batasi percobaan login", "limit maxauth", "set grace time", "audit login limits", "rollback limits").
   - Default Routing: If intent is ambiguous or general (e.g., "cek ssh", "audit sistem"), route to /K01 by default.

2. Initial Action Trigger:
   - Send HTTP POST to the determined target endpoint (/K01 or /K03).
   - Payload: {"requested_intent": "<user_intent>"}

3. HITL Confirmation Handling:
   - If response status is 'pending_confirmation':
     a. Display the 'confirmation_message' to the user.
     b. Wait for explicit user confirmation ('Ya' or 'Tidak').
   - When the user replies with confirmation:
     a. Send HTTP POST to the SAME endpoint used in step 2.
     b. Payload: {"requested_intent": "<user_reply>", "pending_action": "<action_from_previous_step>"}

4. Output Formatting:
   - Always present 'action_logs' to the user in a clear JSON or formatted text structure.
EOF

# ==========================================
# 6. ENVIRONMENT VARIABLES SETUP
# ==========================================
echo -e "${GREEN}[*] Membuat file .env terpisah untuk endpoint /K01 dan /K03...${NC}"

# File .env untuk Endpoint K01 (SSH Root Access)
cat <<EOF > "${HERMES_CONFIG_DIR}/K01.env"
ENDPOINT_ID=K01
HERMES_API_URL=http://127.0.0.1:8000/K01
MODULE_NAME=SSH Root Access Hardening
HERMES_ENV=production
PATH=\$PATH:/usr/local/bin
EOF

# File .env untuk Endpoint K03 (SSH Limits & Timeouts)
cat <<EOF > "${HERMES_CONFIG_DIR}/K03.env"
ENDPOINT_ID=K03
HERMES_API_URL=http://127.0.0.1:8000/K03
MODULE_NAME=SSH Attempt Limits & Timeout Hardening
HERMES_ENV=production
PATH=\$PATH:/usr/local/bin
EOF

# File .env default
cp "${HERMES_CONFIG_DIR}/K01.env" "${HERMES_CONFIG_DIR}/.env"

# Pastikan kepemilikan seluruh folder & file konfigurasi dimiliki oleh yoru-agent
# Pastikan kepemilikan seluruh folder & file konfigurasi dimiliki oleh yoru-agent
chown -R "${TARGET_USER}:${TARGET_USER}" "${USER_HOME}/.config"
echo -e "${GREEN}[OK] System Instruction & Konfigurasi .env (/K01 & /K03) disimpan di ${HERMES_CONFIG_DIR}${NC}"

echo -e "\n${GREEN}=== SETUP HERMES AGENT SELESAI ===${NC}"
echo "Ringkasan:"
echo "1. Target User        : $TARGET_USER"
echo "2. Taskfile installed : $(command -v task)"
echo "3. Sudoers file       : $SUDOERS_FILE"
echo "4. System Instructions: ${HERMES_CONFIG_DIR}/system_instruction.txt"
echo "5. Endpoints Active   : /K01 (${HERMES_CONFIG_DIR}/K01.env) & /K03 (${HERMES_CONFIG_DIR}/K03.env)"