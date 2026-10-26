"""Stable CLI entrypoint; implementation lives in app.workers.notifications."""

import logging

from telelink_common.logging import configure_logging

from app.workers.notifications import main

if __name__ == "__main__":
    try:
        main()
    except Exception:
        configure_logging("ERROR")
        logging.getLogger(__name__).exception("notification_worker_failed")
        raise SystemExit(1) from None
