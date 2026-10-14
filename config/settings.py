from pathlib import Path

AGENT_NAME = "Yoru-Agent"
VERSION = "1.0.0"

# Direktori utama
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Plan Direktori untuk Hardening dan dan rollback
PLANS_DIR = PROJECT_ROOT / "storage" / "plans"

# Path konfigurasi layanan utama
SSHD_CONFIG = Path("/etc/ssh/sshd_config")
JOURNALD_CONFIG = Path("/etc/systemd/journald.conf")
JOURNALD_DROPIN_DIR = Path("/etc/systemd/journald.conf.d")
JOURNAL_LOG_DIR = Path("/var/log/journal")

# Daftar Layanan
JOURNALD_SERVICE_NAME = "systemd-journald"

# Daftar shell yang tidak valid / dibatasi untuk akses login
INVALID_SHELLS = {"/bin/false", "/usr/sbin/nologin", "/sbin/nologin", "/bin/sync"}

# Direktori backup
SSH_BACKUP_DIR = Path("/var/backups/yoru-agent/ssh")
JOURNALD_BACKUP_DIR = Path("/var/backups/yoru-agent/journald")

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

# Daftar layanan yang disetujui (Approved Services) untuk Katalog K11
APPROVED_SERVICES_SET = {
    "sshd",
    "ntpd",
    "uwsgi",
    "chronyd",
    "systemd-resolve"
}

# Target nilai SystemMaxUse untuk Katalog K14
TARGET_SYSTEM_MAX_USE = "500M"

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
    "K12": "journald_service",
    "K13": "journald_log_access",
    "K14": "journald_compress",
    "K15": "journald_storage",
    "K16": "icmp_broadcast",
    "K17": "icmp_redirects",
    "K18": "source_route",
    "K19": "tcp_syncookies",
}