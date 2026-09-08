#!/bin/bash
# setup_hermes_agent.sh - Skrip Otomasi Konfigurasi Environment Hermes Agent

set -e

# Warna untuk output terminal
GREEN='\033[0;32m'
NC='\033[0m' # No Color
RED='\033[0;31m'

echo -e "${GREEN}[*] Memulai Setup Environment Hermes Agent...${NC}"

# 1. Pastikan skrip dijalankan dengan akses root/sudo
if [ "$EUID" -ne 0 ]; then
  echo -e "${RED}[ERROR] Skrip ini harus dijalankan dengan sudo atau sebagai root.${NC}"
  exit 1
fi

# Dapatkan nama user asli jika dijalankan menggunakan sudo
TARGET_USER=${SUDO_USER:-$USER}
USER_HOME=$(getent passwd "$TARGET_USER" | cut -d: -f6)

echo -e "${GREEN}[*] Target User System: ${TARGET_USER}${NC}"

# ==========================================
# 2. INSTALASI TASKFILE CLI (Task Runner)
# ==========================================
if ! command -v task &> /dev/null; then
    echo -e "${GREEN}[*] Menginstall Taskfile CLI...${NC}"
    sh -c "$(curl --location https://taskfile.dev/install.sh)" -- -d -b /usr/local/bin
    echo -e "${GREEN}[OK] Taskfile CLI berhasil diinstall.${NC}"
else
    echo -e "${GREEN}[OK] Taskfile CLI sudah terinstall.${NC}"
fi

# ==========================================
# 3. KONFIGURASI SUDOERS (NOPASSWD)
# ==========================================
# Memastikan user bisa mengeksekusi sudo systemctl restart sshd tanpa minta password
SUDOERS_FILE="/etc/sudoers.d/hermes_agent_${TARGET_USER}"

echo -e "${GREEN}[*] Mengonfigurasi izin Sudoers tanpa password untuk user ${TARGET_USER}...${NC}"
cat <<EOF > "$SUDOERS_FILE"
# Izin NOPASSWD untuk otomatisasi Hermes Agent & Taskfile
${TARGET_USER} ALL=(ALL) NOPASSWD: ALL
EOF

chmod 0440 "$SUDOERS_FILE"
echo -e "${GREEN}[OK] Konfigurasi sudoers tersimpan di $SUDOERS_FILE${NC}"

# ==========================================
# 4. MEMBUAT FILE PROMPT SYSTEM INSTRUCTION
# ==========================================
HERMES_CONFIG_DIR="${USER_HOME}/.config/hermes-agent"
mkdir -p "$HERMES_CONFIG_DIR"

echo -e "${GREEN}[*] Membuat file System Prompt Hermes Agent...${NC}"
cat <<'EOF' > "${HERMES_CONFIG_DIR}/system_instruction.txt"
[HERMES AGENT SYSTEM INSTRUCTION]
Role: Security Orchestrator for SSH Hardening System

Protocol:
1. When user requests SSH check or general task:
   - Send HTTP POST to FastAPI: http://127.0.0.1:8000/K01
   - Payload: {"requested_intent": "<user_intent>"}

2. When response status is 'pending_confirmation':
   - Present the 'confirmation_message' to the user.
   - Wait for explicit user confirmation ('Ya' or 'Tidak').

3. When user replies with confirmation:
   - Send HTTP POST to FastAPI: http://127.0.0.1:8000/K01
   - Payload: {"requested_intent": "<user_reply>", "pending_action": "<action_from_previous_step>"}

4. Output Formatting:
   - Always present 'action_logs' to the user in a clear JSON or formatted text structure.
EOF

# Sesuaikan kepemilikan folder ke user biasa (non-root)
chown -R "${TARGET_USER}:${TARGET_USER}" "$HERMES_CONFIG_DIR"
echo -e "${GREEN}[OK] System Instruction disimpan di ${HERMES_CONFIG_DIR}/system_instruction.txt${NC}"

# ==========================================
# 5. ENVIRONMENT VARIABLES SETUP
# ==========================================
ENV_FILE="${HERMES_CONFIG_DIR}/.env"
echo -e "${GREEN}[*] Membuat file .env untuk Hermes Agent...${NC}"
cat <<EOF > "$ENV_FILE"
HERMES_API_URL=http://127.0.0.1:8000/K01
HERMES_ENV=production
PATH=\$PATH:/usr/local/bin
EOF

chown "${TARGET_USER}:${TARGET_USER}" "$ENV_FILE"
echo -e "${GREEN}[OK] File .env disimpan di $ENV_FILE${NC}"

echo -e "\n${GREEN}=== SETUP HERMES AGENT SELESAI ===${NC}"
echo "Ringkasan:"
echo "1. Taskfile installed : $(command -v task)"
echo "2. Sudoers file       : $SUDOERS_FILE"
echo "3. System Instructions: ${HERMES_CONFIG_DIR}/system_instruction.txt"
echo "4. Environment File   : $ENV_FILE"