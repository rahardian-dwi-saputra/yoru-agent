import secrets
from fastapi import HTTPException, Security, status
from fastapi.security.api_key import APIKeyHeader
from api.config import AGENT_API_KEY

api_key_header = APIKeyHeader(name="X-API-Key", auto_error=False)


async def verify_api_key(api_key: str = Security(api_key_header)):
    """Memvalidasi API Key dari Header request."""
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Header 'X-API-Key' tidak ditemukan.",
        )

    # Menggunakan compare_digest untuk mencegah Timing Attacks
    if not secrets.compare_digest(api_key, AGENT_API_KEY):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="API Key tidak valid atau tidak diizinkan.",
        )

    return api_key