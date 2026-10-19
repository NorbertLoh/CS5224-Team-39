from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from telelink_common.access import IdentityClient
from telelink_common.auth import TokenVerifier
from telelink_common.errors import install_error_handlers
from telelink_common.middleware import RequestLoggingMiddleware

from app.api import router
from app.database import create_database_engine
from app.settings import Settings
from app.upstream import AdmissionSources


def create_app(settings: Settings | None = None):
    config = settings or Settings()

    @asynccontextmanager
    async def lifespan(app):
        app.state.identity_client = IdentityClient(config)
        app.state.sources = AdmissionSources(config)
        app.state.database_engine = (
            create_database_engine(
                config.database_url.get_secret_value(),
                timeout_seconds=config.database_timeout_seconds,
            )
            if config.database_url
            else None
        )
        try:
            yield
        finally:
            app.state.identity_client.close()
            app.state.sources.close()
            if app.state.database_engine is not None:
                app.state.database_engine.dispose()

    app = FastAPI(
        title="TeleLink consultation",
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
    app.add_middleware(RequestLoggingMiddleware, service="consultation")

    @app.middleware("http")
    async def no_store(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    install_error_handlers(app)
    app.include_router(router)

    @app.get("/health/live")
    def live():
        return {"status": "alive", "service": "consultation"}

    @app.get("/health/ready")
    def ready():
        available = all(
            (
                app.state.database_engine is not None,
                config.auth_issuer,
                config.identity_url,
                config.scheduling_url,
                config.billing_url,
                config.identity_secret,
                config.scheduling_secret,
                config.billing_secret,
                config.signalling_secret,
                config.records_url,
                config.records_secret,
            )
        )
        if available:
            try:
                with app.state.database_engine.connect() as connection:
                    available = (
                        connection.scalar(
                            text("SELECT version_num FROM consultation.alembic_version")
                        )
                        == "0002"
                    )
            except SQLAlchemyError:
                available = False
        return JSONResponse(
            {"status": "ready" if available else "not_ready", "service": "consultation"},
            status_code=200 if available else 503,
        )

    return app
