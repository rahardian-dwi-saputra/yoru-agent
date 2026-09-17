import os
import secrets
from pathlib import Path
from slowapi import Limiter
from slowapi.util import get_remote_address

# Root direktori proyek
API_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = API_DIR.parent
CATALOG_DIR = PROJECT_ROOT / "catalog"
KEY_FILE = API_DIR / "key.txt"

# Rate Limiter Instance
limiter = Limiter(key_func=get_remote_address)

def get_api_key() -> str:
    """Membaca API Key dari file key.txt, environment variable, atau auto-generate temp key."""
    # 1. Coba baca dari file key.txt
    if KEY_FILE.is_file():
        try:
            key = KEY_FILE.read_text(encoding="utf-8").strip()
            if key:
                return key
        except Exception as e:
            print(f"[WARN] Gagal membaca key.txt: {e}")

    # 2. Coba baca dari Environment Variable
    env_key = os.getenv("YORU_API_KEY")
    if env_key:
        return env_key.strip()

    # 3. Fallback jika file key.txt belum digenerate saat setup (agar app tidak crash)
    print("[WARN] key.txt tidak ditemukan! Menggunakan temporary randomly-generated key.")
    return secrets.token_hex(32)


# Simpan API Key aktif
AGENT_API_KEY = get_api_key()