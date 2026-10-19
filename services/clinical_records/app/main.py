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
from app.documents import router as documents_router
from app.mc_documents import router as mc_documents_router
from app.medical_certificates import router as mc_router
from app.settings import Settings
from app.upstream import RecordsUpstream


def create_app(settings: Settings | None = None):
    config = settings or Settings()

    @asynccontextmanager
    async def lifespan(app):
        app.state.identity_client = IdentityClient(config)
        app.state.upstream = RecordsUpstream(config)
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
            app.state.upstream.close()
            if app.state.database_engine is not None:
                app.state.database_engine.dispose()

    app = FastAPI(
        title="TeleLink clinical records",
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
    app.add_middleware(RequestLoggingMiddleware, service="clinical_records")

    # Prevent browser/proxy caches retaining clinical responses and errors.
    @app.middleware("http")
    async def no_store(request, call_next):
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        return response

    install_error_handlers(app)
    app.include_router(router)
    app.include_router(documents_router)
    app.include_router(mc_router)
    app.include_router(mc_documents_router)

    @app.get("/health/live")
    def live():
        return {"status": "alive", "service": "clinical_records"}

    @app.get("/health/ready")
    def ready():
        available = all(
            (
                app.state.database_engine is not None,
                config.auth_issuer,
                config.identity_url,
                config.scheduling_url,
                config.fulfilment_url,
                config.cursor_secret,
                config.consultation_secret,
            )
        )
        if available:
            try:
                with app.state.database_engine.connect() as connection:
                    available = (
                        connection.scalar(
                            text("SELECT version_num FROM clinical_records.alembic_version")
                        )
                        == "0005"
                    )
            except SQLAlchemyError:
                available = False
        return JSONResponse(
            {"status": "ready" if available else "not_ready", "service": "clinical_records"},
            status_code=200 if available else 503,
        )

    return app
