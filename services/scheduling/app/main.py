from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from telelink_common.access import IdentityClient
from telelink_common.auth import TokenVerifier
from telelink_common.errors import install_error_handlers
from telelink_common.middleware import RequestLoggingMiddleware

from app.api import router
from app.appointments import router as appointments_router
from app.booking import router as booking_router
from app.checkout import router as checkout_router
from app.database import create_database_engine
from app.holds import HoldCache
from app.models import Appointment, AvailabilitySlot
from app.settings import Settings
from app.tenant import TenantClient


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings or Settings()

    @asynccontextmanager
    async def lifespan(app):
        app.state.identity_client = IdentityClient(config)
        app.state.tenant_client = TenantClient(config)
        app.state.hold_cache = HoldCache(config)
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
            app.state.tenant_client.close()
            app.state.hold_cache.close()
            if app.state.database_engine is not None:
                app.state.database_engine.dispose()

    app = FastAPI(
        title="TeleLink scheduling",
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
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID", "Retry-After"],
    )
    app.add_middleware(RequestLoggingMiddleware, service="scheduling")
    install_error_handlers(app)
    app.include_router(router)
    app.include_router(booking_router)
    app.include_router(appointments_router)
    app.include_router(checkout_router)

    @app.get("/health/live", tags=["health"])
    def live():
        return {"status": "alive", "service": "scheduling"}

    @app.get("/health/ready", tags=["health"])
    def ready():
        engine = app.state.database_engine
        available = all(
            (
                engine is not None,
                config.auth_issuer,
                config.identity_url,
                config.tenant_url,
                config.scheduling_secret,
                config.cursor_secret,
                config.redis_url,
            )
        )
        if available:
            try:
                with engine.connect() as connection:
                    connection.execute(select(AvailabilitySlot.withdrawn_at).limit(1))
                    connection.execute(select(Appointment.appointment_id).limit(1))
                    available = (
                        connection.scalar(
                            text("SELECT version_num FROM scheduling.alembic_version")
                        )
                        == "0005"
                    )
            except SQLAlchemyError:
                available = False
        available = available and app.state.hold_cache.ready()
        return JSONResponse(
            {"status": "ready" if available else "not_ready", "service": "scheduling"},
            status_code=200 if available else 503,
        )

    return app
