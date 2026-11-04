from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from telelink_common.access import IdentityClient
from telelink_common.auth import TokenVerifier
from telelink_common.errors import install_error_handlers
from telelink_common.middleware import RequestLoggingMiddleware

from app.api.admin import router as admin_router
from app.api.billing_profiles import router as billing_profiles_router
from app.api.clinics import router
from app.api.doctors import router as doctors_router
from app.api.document_profiles import router as document_profiles_router
from app.api.locations import router as locations_router
from app.api.logos import router as logos_router
from app.database import create_database_engine
from app.integrations.logos import LogoStorage
from app.models import AuditEvent, Clinic
from app.settings import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings()

    @asynccontextmanager
    async def lifespan(app):
        app.state.identity_client = IdentityClient(config)
        app.state.logo_storage = LogoStorage(config)
        app.state.database_engine = (
            create_database_engine(
                config.database_url.get_secret_value(),
                timeout_seconds=config.database_timeout_seconds,
            )
            if config.database_url is not None
            else None
        )
        try:
            yield
        finally:
            app.state.identity_client.close()
            app.state.logo_storage.close()
            if app.state.database_engine is not None:
                app.state.database_engine.dispose()
                app.state.database_engine = None

    app = FastAPI(
        title="TeleLink tenant",
        version="0.1.0",
        lifespan=lifespan,
        root_path=config.root_path,
        docs_url="/docs" if config.expose_docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if config.expose_docs else None,
    )
    app.state.settings = config
    app.state.database_engine = None
    app.state.token_verifier = TokenVerifier(config)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID", "Retry-After"],
    )
    app.add_middleware(RequestLoggingMiddleware, service="tenant")
    install_error_handlers(app)

    @app.middleware("http")
    async def cache_policy(request, call_next):
        response = await call_next(request)
        response.headers.setdefault("Cache-Control", "no-store")
        return response

    app.include_router(router)
    app.include_router(doctors_router)
    app.include_router(admin_router)
    app.include_router(logos_router)
    app.include_router(document_profiles_router)
    app.include_router(billing_profiles_router)
    app.include_router(locations_router)

    @app.get("/health/live", tags=["health"])
    def live():
        return {"status": "alive", "service": "tenant"}

    @app.get("/health/ready", tags=["health"])
    def ready(request: Request):
        engine = request.app.state.database_engine
        available = all(
            (
                engine is not None,
                config.auth_issuer,
                config.identity_url,
                config.tenant_secret,
                config.cursor_secret,
                config.scheduling_secret,
            )
        )
        if available:
            try:
                with engine.connect() as connection:
                    connection.execute(select(Clinic.tenant_id).limit(1))
                    connection.execute(select(AuditEvent.event_id).limit(1))
                    available = (
                        connection.scalar(text("SELECT version_num FROM tenant.alembic_version"))
                        == "0004"
                    )
            except SQLAlchemyError:
                available = False
        return JSONResponse(
            {"status": "ready" if available else "not_ready", "service": "tenant"},
            status_code=200 if available else 503,
        )

    return app
