import uvicorn

from app.settings import Settings

settings = Settings()
uvicorn.run(
    "app.main:create_app",
    factory=True,
    host=settings.host,
    port=settings.port,
    log_level=settings.log_level.lower(),
)
