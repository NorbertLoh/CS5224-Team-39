"""Queue a fixed local maintenance job without giving the API admin credentials."""

from telelink_common.errors import DomainError
from telelink_common.file_jobs import FileJobs

from app.services.demo_reset import TERMINAL, ResetControl


class LocalResetControl:
    def __init__(self, root):
        self.jobs = FileJobs(root)

    @staticmethod
    def public(state):
        return {**ResetControl.public(state), "environment": "local"}

    def status(self):
        state = self.jobs.read()
        if not self.jobs.worker_available() and (not state or state["status"] in TERMINAL):
            raise DomainError(
                503, "local_reset_unavailable", "The local reset worker is unavailable."
            )
        return self.public(state)

    def start(self, request_id, actor_id):
        try:
            with self.jobs.claim():
                state = self.jobs.read()
                if state and state["request_id"] == request_id:
                    return self.public(state)
                if state and state["status"] not in TERMINAL:
                    raise DomainError(409, "reset_active", "A local reset is already running.")
                if not self.jobs.worker_available():
                    raise DomainError(
                        503, "local_reset_unavailable", "The local reset worker is unavailable."
                    )
                state = {"request_id": request_id, "actor_id": actor_id}
                self.jobs.update(state, "queued", "Waiting for the local reset worker")
                return self.public(state)
        except FileExistsError:
            state = self.jobs.read()
            if state and state["request_id"] == request_id:
                return self.public(state)
            raise DomainError(409, "reset_active", "Another local reset holds the claim.") from None
