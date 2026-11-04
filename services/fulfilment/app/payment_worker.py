"""Stable CLI entrypoint; implementation lives in app.workers.payments."""

from app.workers.payments import main

if __name__ == "__main__":
    main()
