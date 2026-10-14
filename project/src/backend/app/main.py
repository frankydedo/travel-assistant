import logging
import time
import uuid

from fastapi import FastAPI, Request

from app.api.routes import router
from app.config import get_settings
from app.logging_setup import configure_logging, request_id_var

settings = get_settings()
configure_logging(settings.log_level, settings.log_format)
log = logging.getLogger("app.http")

app = FastAPI(
    title="Assistente viaggi API",
    description="Backend dell'assistente conversazionale per viaggi personalizzati.",
    version="0.1.0",
)
app.include_router(router)


def _valid_uuid(value: str | None) -> str | None:
    """Request ids are UUIDs too: a caller-supplied X-Request-ID is accepted only if it is one."""
    try:
        return str(uuid.UUID(value)) if value else None
    except ValueError:
        return None


@app.middleware("http")
async def request_context(request: Request, call_next):
    """One request id per request (or the caller's X-Request-ID), on every log line and in the response."""
    request_id = _valid_uuid(request.headers.get("x-request-id")) or str(uuid.uuid4())
    token = request_id_var.set(request_id)
    started = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        log.exception("http.unhandled_error", extra={"method": request.method, "path": request.url.path})
        raise
    finally:
        request_id_var.reset(token)
    response.headers["X-Request-ID"] = request_id
    if request.url.path != "/api/health":
        level = logging.WARNING if response.status_code >= 500 else logging.INFO
        log.log(
            level,
            "http.request",
            extra={
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "status": response.status_code,
                "duration_ms": round((time.perf_counter() - started) * 1000),
            },
        )
    return response
