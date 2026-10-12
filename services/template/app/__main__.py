import uvicorn

from app.logging import configure_logging
from app.main import create_app
from app.settings import Settings


def main() -> None:
    settings = Settings()
    configure_logging(settings.log_level)
    uvicorn.run(
        create_app(settings), host=settings.host, port=settings.port,
        log_config=None, access_log=False,
    )


if __name__ == "__main__":
    main()
