import os
import secrets
from slowapi import Limiter
from slowapi.util import get_remote_address

from config.api import API_KEY_PATH

# Rate Limiter Instance
limiter = Limiter(key_func=get_remote_address)

def get_api_key() -> str:
    """Membaca API Key dari file key.txt, environment variable, atau auto-generate temp key."""
    # 1. Coba baca dari file key.txt
    if API_KEY_PATH.is_file():
        try:
            key = API_KEY_PATH.read_text(encoding="utf-8").strip()
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