import uvicorn
from fastapi import FastAPI

from api.routers import catalog
from config.api import API_HOST, API_PORT, ALLOWED_ORIGINS, DEBUG_MODE

app = FastAPI(
    title="Yoru Agent API",
    description="API Universal untuk Audit, Hardening, dan Rollback Konfigurasi Server Keamanan",
    version="1.0.0",
)

# Register Router
app.include_router(catalog.router)

if __name__ == "__main__":
    uvicorn.run("api.main:app", host=API_HOST, port=API_PORT, reload=DEBUG_MODE)