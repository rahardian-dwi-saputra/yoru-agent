from pathlib import Path
from dotenv import load_dotenv
import sys
import uvicorn

# Project root
PROJECT_ROOT = Path(__file__).resolve().parents[1]

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from api.routers import catalog, logs, ai_advisor
from config.api import API_HOST, API_PORT, ALLOWED_ORIGINS, DEBUG_MODE

load_dotenv(PROJECT_ROOT / ".env")

app = FastAPI(
    title="Yoru Agent API",
    description="API Universal untuk Audit, Hardening, dan Rollback Konfigurasi Server Keamanan",
    version="1.0.0",
)

# Konfigurasi CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],           
    allow_headers=["*"],          
)

# Register Router
app.include_router(catalog.router)
app.include_router(logs.router)
app.include_router(ai_advisor.router)

if __name__ == "__main__":
    uvicorn.run(
        "api.main:app", 
        host=API_HOST, 
        port=API_PORT, 
        reload=DEBUG_MODE,
        app_dir=str(PROJECT_ROOT),
    )