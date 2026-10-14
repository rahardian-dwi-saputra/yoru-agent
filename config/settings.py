from pathlib import Path

AGENT_NAME = "Yoru-Agent"
VERSION = "1.0.0"

# Direktori utama
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# --- PLANS DIRECTORIES ---
PLANS_DIR = PROJECT_ROOT / "plans"
HARDENING_PLANS_DIR = PLANS_DIR / "hardening"
ROLLBACK_PLANS_DIR = PLANS_DIR / "rollback"

HARDENING_PLANS_DIR.mkdir(parents=True, exist_ok=True)
ROLLBACK_PLANS_DIR.mkdir(parents=True, exist_ok=True)

# Path konfigurasi layanan utama
SSHD_CONFIG = Path("/etc/ssh/sshd_config")

# Daftar shell yang tidak valid / dibatasi untuk akses login
INVALID_SHELLS = {"/bin/false", "/usr/sbin/nologin", "/sbin/nologin", "/bin/sync"}

# Direktori backup
SSH_BACKUP_DIR = Path("/var/backups/yoru-agent/ssh")

# Daftar layanan yang disetujui (Approved Services) untuk Katalog K11
APPROVED_SERVICES = [
    "ssh",
    "ntpd",
    "uwsgi",
    "systemd-resolve"
]

# Pemetaan nama Lock File untuk setiap Katalog (K01 - K19)
CATALOG_LOCKS = {
    "K01": "ssh_root_login",
    "K02": "ssh_password_auth",
    "K03": "ssh_login_grace_time",
    "K04": "ssh_max_auth_tries",
    "K05": "ssh_ciphers",
    "K06": "ssh_macs",
    "K07": "ssh_kex_algorithms",
    "K08": "auditd_service",
    "K09": "ufw_service",
    "K10": "ufw_default_deny",
    "K11": "approved_services_listening",
    "K12": "journald_storage",
    "K13": "journald_service",
    "K14": "journald_log_access",
    "K15": "journald_compress",
    "K16": "icmp_broadcast",
    "K17": "icmp_redirects",
    "K18": "source_route",
    "K19": "tcp_syncookies",
}