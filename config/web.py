from __future__ import annotations
from config.settings import PROJECT_ROOT

WEB_HOST="0.0.0.0"
WEB_PORT="8501"

# Direktori penyimpanan Web Dashboard
WEB_STORAGE_DIR = PROJECT_ROOT / "storage" / "web"

# Lokasi database SQLite
DATABASE_PATH = WEB_STORAGE_DIR / "web_cache.db"