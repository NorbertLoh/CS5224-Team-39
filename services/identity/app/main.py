from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from telelink_common.auth import TokenVerifier
from telelink_common.errors import install_error_handlers
from telelink_common.middleware import RequestLoggingMiddleware

from app.api import router
from app.clinics import ClinicDirectory
from app.database import create_database_engine
from app.doctors import router as doctors_router
from app.document_profiles import router as document_profiles_router
from app.models import Membership, Subject
from app.notification_context import router as notification_router
from app.provisioning import router as provisioning_router
from app.settings import Settings


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings()

    @asynccontextmanager
    async def lifespan(app):
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
            app.state.clinic_directory.close()
            if app.state.database_engine is not None:
                app.state.database_engine.dispose()
                app.state.database_engine = None

    app = FastAPI(
        title="TeleLink identity",
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
    app.state.clinic_directory = ClinicDirectory(config)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_methods=["GET", "PUT", "DELETE", "POST"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID", "Retry-After"],
    )
    app.add_middleware(RequestLoggingMiddleware, service="identity")
    app.include_router(notification_router)
    install_error_handlers(app)
    app.include_router(router)
    app.include_router(provisioning_router)
    app.include_router(doctors_router)
    app.include_router(document_profiles_router)

    @app.get("/health/live", tags=["health"])
    def live():
        return {"status": "alive", "service": "identity"}

    @app.get("/health/ready", tags=["health"])
    def ready(request: Request):
        engine = request.app.state.database_engine
        available = (
            engine is not None
            and config.auth_issuer is not None
            and config.cursor_secret is not None
        )
        if available:
            try:
                with engine.connect() as connection:
                    connection.execute(select(Subject.subject_id).limit(1))
                    connection.execute(select(Membership.membership_id).limit(1))
                    available = (
                        connection.scalar(text("SELECT version_num FROM identity.alembic_version"))
                        == "0002"
                    )
            except SQLAlchemyError:
                available = False
        return JSONResponse(
            {"status": "ready" if available else "not_ready", "service": "identity"},
            status_code=200 if available else 503,
        )

    return app
