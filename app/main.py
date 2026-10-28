import logging
from time import perf_counter
from uuid import uuid4

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.concurrency import run_in_threadpool
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from .api.api import api_router
from .modules.log.services import (
    record_error,
    record_exception,
    record_request_metrics,
)

logger = logging.getLogger(__name__)
app = FastAPI(title="Noema API", version="1.0")

@app.get("/")
def root() -> dict[str, str]:
    return {"message": "Noema API is running."}


@app.exception_handler(IntegrityError)
async def integrity_error_handler(
    request: Request, exc: IntegrityError
) -> JSONResponse:
    logger.warning("Database integrity error on %s", request.url.path)
    if not getattr(request.state, "error_logged", False):
        await run_in_threadpool(
            record_exception, request, status.HTTP_409_CONFLICT, exc
        )
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={"detail": "The requested change conflicts with existing data."},
        headers={"X-Request-ID": getattr(request.state, "request_id", "")},
    )


@app.exception_handler(SQLAlchemyError)
async def database_error_handler(
    request: Request, exc: SQLAlchemyError
) -> JSONResponse:
    logger.error("Database error on %s", request.url.path, exc_info=exc)
    if not getattr(request.state, "error_logged", False):
        await run_in_threadpool(
            record_exception, request, status.HTTP_503_SERVICE_UNAVAILABLE, exc
        )
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"detail": "The database is temporarily unavailable."},
        headers={"X-Request-ID": getattr(request.state, "request_id", "")},
    )


@app.exception_handler(Exception)
async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error("Unhandled error on %s", request.url.path, exc_info=exc)
    if not getattr(request.state, "error_logged", False):
        await run_in_threadpool(
            record_exception, request, status.HTTP_500_INTERNAL_SERVER_ERROR, exc
        )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error."},
        headers={"X-Request-ID": getattr(request.state, "request_id", "")},
    )


@app.middleware("http")
async def request_metrics_middleware(
    request: Request,
    call_next: RequestResponseEndpoint,
) -> Response:
    request_id = str(uuid4())
    request.state.request_id = request_id
    start_time = perf_counter()

    try:
        response = await call_next(request)
    except Exception as exc:
        duration_ms = (perf_counter() - start_time) * 1000
        await run_in_threadpool(
            record_request_metrics,
            request,
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            duration_ms,
        )
        if not getattr(request.state, "error_logged", False):
            await run_in_threadpool(
                record_exception,
                request,
                status.HTTP_500_INTERNAL_SERVER_ERROR,
                exc,
            )
        raise

    duration_ms = (perf_counter() - start_time) * 1000
    response.headers["X-Request-ID"] = request_id
    await run_in_threadpool(
        record_request_metrics,
        request,
        response.status_code,
        duration_ms,
    )
    if response.status_code >= 400 and not getattr(request.state, "error_logged", False):
        await run_in_threadpool(
            record_error,
            request,
            response.status_code,
            "HTTPError",
            f"HTTP response returned status {response.status_code}",
        )
    return response


app.include_router(api_router)