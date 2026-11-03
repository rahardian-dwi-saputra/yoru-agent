from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo

AGENT_NAME = "Yoru-Agent"
VERSION = "1.0.0"

# Timezone untuk pencatatan log
TIMEZONE_NAME = "Asia/Jakarta"
APP_TIMEZONE = ZoneInfo(TIMEZONE_NAME)

# Direktori utama
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Plan Direktori untuk Hardening dan dan rollback
PLANS_DIR = PROJECT_ROOT / "storage" / "plans"

# Path konfigurasi layanan utama
SSHD_CONFIG = Path("/etc/ssh/sshd_config")
JOURNALD_CONFIG = Path("/etc/systemd/journald.conf.d/journald-yoru-agent.conf")
JOURNAL_LOG_DIR = Path("/var/log/journal")
SYSCTL_CONF = Path("/etc/sysctl.d/60-cis-icmp-broadcast.conf")

# Direktori backup
SSH_BACKUP_DIR = Path("/var/backups/yoru-agent/ssh")
JOURNAL_ACCESS_BACKUP = Path("/var/lib/yoru-agent/backups/journald-access.json")
JOURNALD_BACKUP_DIR = Path("/var/backups/yoru-agent/journald")

# Daftar Nama Package
AUDITD_PACKAGE_NAME = "auditd"
UFW_PACKAGE_NAME = "ufw"

# Daftar Nama Layanan
SSH_SERVICE_NAME = ["ssh", "sshd"]
AUDITD_SERVICE_NAME = "auditd"
UFW_SERVICE_NAME = "ufw"
JOURNALD_SERVICE_NAME = "systemd-journald"

# Daftar shell yang tidak valid / dibatasi untuk akses login
INVALID_SHELLS = {"/bin/false", "/usr/sbin/nologin", "/sbin/nologin", "/bin/sync"}

# Daftar Ciphers untuk Katalog K05
APPROVED_CIPHERS_LIST = [
    "chacha20-poly1305@openssh.com",
    "aes256-gcm@openssh.com",
    "aes128-gcm@openssh.com",
    "aes256-ctr",
    "aes192-ctr",
    "aes128-ctr",
]

# Daftar MACs untuk Katalog K06
APPROVED_MACS_LIST = [
    "hmac-sha2-512-etm@openssh.com",
    "hmac-sha2-256-etm@openssh.com",
    "umac-128-etm@openssh.com",
    "hmac-sha2-512",
    "hmac-sha2-256",
    "umac-128@openssh.com",
]

# Daftar KexAlgorithms untuk Katalog K07
APPROVED_KEX_LIST = [
    "curve25519-sha256",
    "curve25519-sha256@libssh.org",
    "diffie-hellman-group14-sha256",
    "diffie-hellman-group16-sha512",
    "diffie-hellman-group18-sha512",
    "ecdh-sha2-nistp256",
    "ecdh-sha2-nistp384",
    "ecdh-sha2-nistp521",
    "sntrup761x25519-sha512@openssh.com",
]

# Baseline rotasi log journald untuk Katalog K11
JOURNALD_ROTATION_BASELINE = {
    "SystemMaxUse": "1G",
    "SystemKeepFree": "500M",
    "RuntimeMaxUse": "200M",
    "RuntimeKeepFree": "50M",
    "MaxFileSec": "1month",
}

# Daftar layanan yang disetujui (Approved Services) untuk Katalog K15
APPROVED_SERVICES_SET = {
    # Yoru-Agent Backend
    "uvicorn",

    # Yoru-Agent Web Dashboard
    "streamlit",

    # Python Runtime
    "python",
    "python3",
    
    # Remote Administration
    "sshd",

    # Web server
    "nginx",
    "apache2",

    # System Services
    "systemd-resolve",
}

# Konfigurasi Hardening Kernel SYSCTL untuk Katalog K16
SYSCTL_KEY_ICMP_ECHO_BROADCASTS = "net.ipv4.icmp_echo_ignore_broadcasts"
SYSCTL_TARGET_ICMP_ECHO_BROADCASTS = "1"
SYSCTL_DEFAULT_ICMP_ECHO_BROADCASTS = "0"

# Konfigurasi Hardening Kernel SYSCTL untuk Katalog K17
SYSCTL_KEYS_ACCEPT_REDIRECTS = [
    "net.ipv4.conf.all.accept_redirects",
    "net.ipv4.conf.default.accept_redirects",
]
SYSCTL_TARGET_ACCEPT_REDIRECTS = "0"
SYSCTL_DEFAULT_ACCEPT_REDIRECTS = "1"

# Konfigurasi Hardening Kernel SYSCTL untuk Katalog K18
SYSCTL_KEYS_ACCEPT_SOURCE_ROUTE = [
    "net.ipv4.conf.all.accept_source_route",
    "net.ipv4.conf.default.accept_source_route",
]
SYSCTL_TARGET_ACCEPT_SOURCE_ROUTE = "0"
SYSCTL_DEFAULT_ACCEPT_SOURCE_ROUTE = "1"

# Konfigurasi Hardening Kernel SYSCTL untuk Katalog K19
SYSCTL_KEY_TCP_SYNCOOKIES = "net.ipv4.tcp_syncookies"
SYSCTL_TARGET_TCP_SYNCOOKIES = "1"
SYSCTL_DEFAULT_TCP_SYNCOOKIES = "0"


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
    "K09": "journald_log_access",
    "K10": "journald_storage",
    "K11": "journald_log_rotation",
    "K12": "system_updates_audit",
    "K13": "ufw_service",
    "K14": "ufw_default_deny",
    "K15": "approved_services_listening",
    "K16": "icmp_broadcast",
    "K17": "icmp_redirects",
    "K18": "source_route",
    "K19": "tcp_syncookies",
}

# Helper function untuk mendapatkan waktu saat ini
def get_current_time():
    return datetime.now(APP_TIMEZONE)

def get_current_isoformat():
    """Mengembalikan string timestamp ISO 8601 dengan offset +07:00."""
    return datetime.now(APP_TIMEZONE).isoformat()