"""Small on-disk job mailbox shared by an API and a separate local worker."""

import json
import os
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


class FileJobs:
    def __init__(self, root):
        self.root = Path(root)

    def read(self):
        try:
            return json.loads((self.root / "state.json").read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None

    def write(self, state):
        temporary = self.root / f"state-{uuid4()}.tmp"
        try:
            with temporary.open("x", encoding="utf-8") as output:
                json.dump(state, output)
                output.flush()
                os.fsync(output.fileno())
            temporary.replace(self.root / "state.json")
        finally:
            temporary.unlink(missing_ok=True)

    def update(self, state, status, stage):
        state.update(status=status, stage=stage, updated_at=datetime.now(timezone.utc).isoformat())
        self.write(state)

    @contextmanager
    def claim(self):
        lock = self.root / "claim"
        lock.mkdir()
        try:
            yield
        finally:
            lock.rmdir()

    def heartbeat(self):
        (self.root / "heartbeat").touch()

    def worker_available(self):
        try:
            age = datetime.now(timezone.utc).timestamp() - (self.root / "heartbeat").stat().st_mtime
        except FileNotFoundError:
            return False
        # Filesystem timestamps can be rounded slightly ahead of the clock read.
        return -2 <= age < 15
