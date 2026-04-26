"""FastAPI application factory and exception handlers."""

from __future__ import annotations

import logging
import time
import uuid
from collections.abc import Awaitable, Callable

from fastapi import FastAPI, Request, Response, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from runllm.api.routers import chat as chat_router
from runllm.api.routers import garmin as garmin_router
from runllm.api.routers import health as health_router
from runllm.config import get_settings
from runllm.garmin.exceptions import GarminAuthError, GarminMfaRequiredError
from runllm.llm.exceptions import LLMError
from runllm.logging_config import setup_logging

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    """Build a fully-configured :class:`FastAPI` instance."""

    settings = get_settings()
    setup_logging(settings.log_level)

    app = FastAPI(
        title="RunLLM",
        description="Personal AI running coach wrapping Garmin Connect with Claude.",
        version="0.1.0",
    )

    origins = [o.strip() for o in settings.allowed_origins.split(",") if o.strip()]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def _request_id_middleware(
        request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        start = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            logger.exception("request_id=%s unhandled error", request_id)
            raise
        duration_ms = (time.perf_counter() - start) * 1000.0
        response.headers["x-request-id"] = request_id
        logger.info(
            "request_id=%s method=%s path=%s status=%d duration_ms=%.1f",
            request_id,
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
        )
        return response

    @app.exception_handler(GarminMfaRequiredError)
    async def _mfa_handler(_: Request, __: GarminMfaRequiredError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"detail": "mfa_required"},
        )

    @app.exception_handler(GarminAuthError)
    async def _garmin_auth_handler(_: Request, exc: GarminAuthError) -> JSONResponse:
        return JSONResponse(status_code=status.HTTP_401_UNAUTHORIZED, content={"detail": str(exc)})

    @app.exception_handler(LLMError)
    async def _llm_handler(_: Request, exc: LLMError) -> JSONResponse:
        return JSONResponse(status_code=status.HTTP_502_BAD_GATEWAY, content={"detail": str(exc)})

    @app.exception_handler(RequestValidationError)
    async def _validation_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"detail": exc.errors()},
        )

    app.include_router(health_router.router)
    app.include_router(garmin_router.router, prefix="/api/v1")
    app.include_router(chat_router.router, prefix="/api/v1")

    return app
