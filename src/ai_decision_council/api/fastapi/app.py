"""FastAPI app factory for ai-decision-council."""

from __future__ import annotations

import logging
from typing import Callable
from uuid import uuid4

from ai_decision_council.client import Council
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .backends import AuthBackend, FileStorageBackend, StaticTokenAuthBackend, StorageBackend
from .helpers import _error_response, _make_envelope
from .rate_limiter import InMemoryRateLimiter
from .router import create_router
from .settings import APISettings

logger = logging.getLogger(__name__)


def create_app(
    *,
    settings: APISettings | None = None,
    storage_backend: StorageBackend | None = None,
    auth_backend: AuthBackend | None = None,
    council_factory: Callable[[], Council] | None = None,
) -> FastAPI:
    """Create a reusable FastAPI app for hosted deployments."""

    resolved_settings = settings or APISettings.from_env()
    resolved_storage = storage_backend or FileStorageBackend(resolved_settings.data_dir)
    resolved_auth = auth_backend or StaticTokenAuthBackend.from_env()
    resolved_council_factory = council_factory or Council.from_env
    rate_limiter = InMemoryRateLimiter()

    app = FastAPI(
        title=resolved_settings.app_title,
        description=resolved_settings.app_description,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(resolved_settings.cors_origins),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_context_middleware(request: Request, call_next):
        request_id = request.headers.get("x-request-id") or str(uuid4())
        request.state.request_id = request_id

        if request.url.path.startswith(resolved_settings.api_prefix):
            try:
                request.state.auth_context = await resolved_auth.authenticate(request)
            except HTTPException as exc:
                if exc.status_code == 401:
                    response = _error_response(
                        request,
                        status_code=401,
                        code="unauthorized",
                        message="Unauthorized.",
                    )
                    response.headers["WWW-Authenticate"] = "Bearer"
                    return response
                if exc.status_code == 503:
                    logger.error("FastAPI auth backend is not configured.")
                    return _error_response(
                        request,
                        status_code=503,
                        code="service_misconfigured",
                        message="Reference API auth is not configured.",
                    )
                return _error_response(
                    request,
                    status_code=exc.status_code,
                    code="auth_error",
                    message=str(exc.detail),
                )

        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    @app.exception_handler(HTTPException)
    async def http_error_handler(request: Request, exc: HTTPException) -> JSONResponse:
        message = str(exc.detail)
        if exc.status_code >= 500:
            message = "Internal server error."
        return _error_response(
            request,
            status_code=exc.status_code,
            code="http_error",
            message=message,
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, _exc: Exception) -> JSONResponse:
        logger.exception(
            "Unhandled request failure request_id=%s path=%s",
            getattr(request.state, "request_id", "unknown"),
            request.url.path,
        )
        return _error_response(
            request,
            status_code=500,
            code="internal_error",
            message="Internal server error.",
        )

    @app.get("/")
    async def root(request: Request):
        return _make_envelope(
            request,
            data={"status": "ok", "service": resolved_settings.app_title},
        )

    router = create_router(
        settings=resolved_settings,
        storage_backend=resolved_storage,
        rate_limiter=rate_limiter,
        council_factory=resolved_council_factory,
    )
    app.include_router(router, prefix=resolved_settings.api_prefix)
    return app
