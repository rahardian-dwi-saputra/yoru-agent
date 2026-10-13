from pathlib import Path

# Direktori utama
BASE_DIR = Path(__file__).resolve().parent.parent

# Path konfigurasi layanan utama
SSHD_CONFIG = Path("/etc/ssh/sshd_config")

# Daftar shell yang tidak valid / dibatasi untuk akses login
INVALID_SHELLS = {"/bin/false", "/usr/sbin/nologin", "/sbin/nologin", "/bin/sync"}

# Direktori backup
SSH_BACKUP_DIR = Path("/var/backups/yoru-agent/ssh")

# Daftar layanan yang disetujui (Approved Services) untuk Katalog K11
APPROVED_SERVICES = [
    "ssh",
    "nginx",
    "uwsgi",
    "postgresql"
]

# Konfigurasi global lainnya
AGENT_NAME = "Yoru-Agent"
VERSION = "1.0.0"

# Pemetaan nama Lock File untuk setiap Katalog (K01 - K19)
CATALOG_LOCKS = {
    "K01": "ssh_root_login",
    "K02": "ssh_password_auth",
    "K16": "icmp_broadcast",
    "K17": "icmp_redirects",
    "K18": "source_route",
    "K19": "tcp_syncookies",
    
}