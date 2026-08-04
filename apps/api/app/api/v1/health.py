from fastapi import APIRouter

from app.db.session import check_database_connection
from app.schemas.health import HealthResponse

router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def health_check() -> HealthResponse:
    db_ok, _ = check_database_connection()
    return HealthResponse(
        status="ok" if db_ok else "degraded",
        database="connected" if db_ok else "unavailable",
        version="0.1.0",
    )
