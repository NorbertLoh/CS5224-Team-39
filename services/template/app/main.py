import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.health import router as health_router
from app.middleware import RequestLoggingMiddleware
from app.settings import Settings

logger = logging.getLogger("telelink.lifecycle")


def create_app(settings: Settings | None = None) -> FastAPI:
    config = settings if settings is not None else Settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # Future tasks initialise service-owned resources here before becoming ready.
        app.state.ready = True
        logger.info("service_started", extra={"service": config.name})
        try:
            yield
        finally:
            app.state.ready = False
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
    app.add_middleware(RequestLoggingMiddleware, service=config.name)
    app.include_router(health_router)
    return app
