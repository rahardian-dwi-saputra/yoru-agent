from __future__ import annotations
from config.settings import PROJECT_ROOT
import os
from dotenv import load_dotenv

load_dotenv()

CATALOGS_DIR = PROJECT_ROOT / "catalog"

API_DIR = PROJECT_ROOT / "api"
API_KEY_PATH = API_DIR / "key.txt"

# Konfigurasi Server FastAPI
API_HOST = "0.0.0.0"
API_PORT = 8000
DEBUG_MODE = True

# CORS Origins yang diizinkan (untuk keamanan dashboard web)

_env_origins = os.getenv("ALLOWED_ORIGINS")

if _env_origins:
    # Jika di .env diatur berupa string yang dipisahkan koma (misal: "http://example.com,https://myip.com")
    ALLOWED_ORIGINS = [
        origin.strip() 
        for origin in _env_origins.split(",") 
        if origin.strip()
    ]
else:
    # Default jika variabel .env belum diset
    ALLOWED_ORIGINS = [
        "http://localhost",
        "http://localhost:3000",
        "http://127.0.0.1:8000"
    ]