from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from telelink_common.access import IdentityClient
from telelink_common.auth import TokenVerifier
from telelink_common.aws import create_client
from telelink_common.errors import install_error_handlers
from telelink_common.middleware import RequestLoggingMiddleware

from app.access import AppointmentClient
from app.api.documents import router
from app.api.notification_context import router as notification_router
from app.database import create_database_engine
from app.services.downloads import Downloads, create_signer
from app.settings import Settings


def create_app(settings: Settings | None = None):
    config = settings or Settings()

    @asynccontextmanager
    async def lifespan(app):
        app.state.identity_client = IdentityClient(config)
        app.state.appointments = AppointmentClient(config)
        app.state.database_engine = (
            create_database_engine(
                config.database_url.get_secret_value(),
                timeout_seconds=config.database_timeout_seconds,
            )
            if config.database_url
            else None
        )
        storage, signer = None, None
        try:
            storage = create_client("s3", config)
            signer = create_signer(config)
            app.state.downloads = Downloads(config, storage, signer)
            yield
        finally:
            app.state.identity_client.close()
            app.state.appointments.close()
            if storage is not None:
                storage.close()
            if signer is not None:
                signer.close()
            if app.state.database_engine is not None:
                app.state.database_engine.dispose()

    app = FastAPI(
        title="TeleLink documents",
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
    app.add_middleware(RequestLoggingMiddleware, service="document")

    @app.middleware("http")
    async def no_store(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    app.include_router(notification_router)
    install_error_handlers(app)
    app.include_router(router)

    @app.get("/health/live")
    def live():
        return {"status": "alive", "service": "document"}

    @app.get("/health/ready")
    def ready():
        available = all(
            (
                app.state.database_engine is not None,
                config.auth_issuer,
                config.identity_url,
                config.scheduling_url,
                config.cursor_secret,
            )
        )
        if available:
            try:
                with app.state.database_engine.connect() as connection:
                    available = (
                        connection.scalar(text("SELECT version_num FROM document.alembic_version"))
                        == "0003"
                    )
            except SQLAlchemyError:
                available = False
        return JSONResponse(
            {"status": "ready" if available else "not_ready", "service": "document"},
            status_code=200 if available else 503,
        )

    return app
