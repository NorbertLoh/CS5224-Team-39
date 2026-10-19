from contextlib import asynccontextmanager

from fastapi import FastAPI
from telelink_common.access import IdentityClient
from telelink_common.auth import TokenVerifier
from telelink_common.errors import install_error_handlers
from telelink_common.middleware import RequestLoggingMiddleware

from app.catalogue import router as catalogue_router
from app.database import Database
from app.deliveries import router as deliveries_router
from app.delivery_provider import SandboxQuotes
from app.dispensing import FixtureDispensing, UnavailableDispensing
from app.health import router as health_router
from app.orders import router as orders_router
from app.quotes import router as quotes_router
from app.settings import Settings


def create_app(settings: Settings | None = None):
    config = settings if settings is not None else Settings()

    @asynccontextmanager
    async def lifespan(app):
        try:
            app.state.database = Database(config) if config.database_url is not None else None
            app.state.ready = True
            yield
        finally:
            app.state.ready = False
            app.state.identity_client.close()
            app.state.delivery_quotes.close()
            if app.state.database is not None:
                app.state.database.close()

    app = FastAPI(
        title="TeleLink fulfilment",
        version="0.1.0",
        lifespan=lifespan,
        root_path=config.root_path,
        docs_url="/docs" if config.expose_docs else None,
        redoc_url=None,
        openapi_url="/openapi.json" if config.expose_docs else None,
    )
    app.state.settings = config
    app.state.ready = False
    app.state.database = None
    app.state.identity_client = IdentityClient(config)
    app.state.token_verifier = TokenVerifier(config)
    app.state.delivery_quotes = SandboxQuotes(config)
    app.state.dispensing = (
        FixtureDispensing(config.dispensing_fixture_path)
        if config.dispensing_fixture_path
        else UnavailableDispensing()
    )
    app.add_middleware(RequestLoggingMiddleware, service=config.name)
    app.include_router(health_router)
    app.include_router(catalogue_router)
    app.include_router(orders_router)
    app.include_router(quotes_router)
    app.include_router(deliveries_router)
    install_error_handlers(app)
    return app
