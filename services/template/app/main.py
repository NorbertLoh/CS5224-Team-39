import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.auth import TokenVerifier
from app.auth import router as auth_router
from app.database import Database
from app.health import router as health_router
from app.middleware import RequestLoggingMiddleware
from app.settings import Settings

logger = logging.getLogger("telelink.lifecycle")


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings if settings is not None else Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        try:
            app.state.database = Database(config) if config.database_url is not None else None
            app.state.ready = True
            logger.info("service_started", extra={"service": config.name})
            yield
        finally:
            app.state.ready = False
            if app.state.database is not None:
                app.state.database.close()
                app.state.database = None
            logger.info("service_stopped", extra={"service": config.name})

    app = FastAPI(
        title=f"TeleLink {config.name}",
        version="0.1.0",
        lifespan=lifespan,
        root_path=config.root_path,
        docs_url="/docs" if config.expose_docs else None,
        redoc_url="/redoc" if config.expose_docs else None,
        openapi_url="/openapi.json" if config.expose_docs else None,
    )
    app.state.settings = config
    app.state.ready = False
    app.state.database = None
    app.state.token_verifier = TokenVerifier(config)
    app.add_middleware(RequestLoggingMiddleware, service=config.name)
    app.include_router(health_router)
    app.include_router(auth_router)
    return app
