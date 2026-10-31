"""SQS intake and scheduled dispatch are separate bounded Lambda entrypoints."""

from contextlib import ExitStack

from telelink_common.lambda_runtime import consume_records, database_sessions, load_settings

from app.database import create_database_engine
from app.integrations.email import SESEmailSender
from app.integrations.recipients import RecipientDirectory
from app.models import event_inbox
from app.services.dispatch import dispatch_one, recover_stale
from app.services.intake import QueueNotification
from app.settings import Settings


def intake(event, context):
    settings = load_settings(Settings)
    with ExitStack() as stack:
        sessions = stack.enter_context(database_sessions(settings, create_database_engine))
        directory = RecipientDirectory(settings)
        stack.callback(directory.close)
        return consume_records(
            event, context, sessions, event_inbox, "notification", QueueNotification(directory)
        )


def dispatch(event, context):
    settings = load_settings(Settings)
    with database_sessions(settings, create_database_engine) as sessions:
        sender = SESEmailSender(settings)
        try:
            recover_stale(sessions, settings)
            sent = 0
            # A schedule drains jobs even when no new SQS events arrive.
            while sent < 20 and context.get_remaining_time_in_millis() >= 15_000:
                if not dispatch_one(sessions, sender, settings):
                    break
                sent += 1
            return {"dispatched": sent}
        finally:
            sender.client.close()
