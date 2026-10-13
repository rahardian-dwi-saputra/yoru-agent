from pathlib import Path

# Base Path Proyek
BASE_DIR = Path(__file__).resolve().parent.parent
CATALOGS_DIR = BASE_DIR / "catalogs"

# Konfigurasi Server FastAPI
API_HOST = "127.0.0.1"
API_PORT = 8000
DEBUG_MODE = True

# CORS Origins yang diizinkan (untuk keamanan dashboard web)
ALLOWED_ORIGINS = [
    "http://localhost",
    "http://localhost:3000",  # Contoh port frontend dashboard
    "http://127.0.0.1:8000"
]