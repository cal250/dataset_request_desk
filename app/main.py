from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, status
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db_session
from app.request_logging import configure_logging, structured_request_log
from app.routes.analytics import router as analytics_router
from app.routes.assignments import router as assignments_router
from app.routes.auth import router as auth_router
from app.routes.episodes import router as episodes_router
from app.routes.requests import router as requests_router

settings = get_settings()
configure_logging(settings.log_level)

app = FastAPI(title="Dataset Request Desk", version="0.1.0")
app.middleware("http")(structured_request_log)
app.include_router(analytics_router)
app.include_router(auth_router)
app.include_router(assignments_router)
app.include_router(episodes_router)
app.include_router(requests_router)


@app.get("/health")
def health_check(session: Annotated[Session, Depends(get_db_session)]) -> dict[str, str]:
    try:
        session.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - requires an unavailable database.
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database is unavailable",
        ) from exc
    return {"status": "ok"}

