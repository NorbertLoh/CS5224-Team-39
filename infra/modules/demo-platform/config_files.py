"""ECS command prelude: materialize configured delivery coverage, then exec the app.

Executed only inside the owning fulfilment container. Secret values never appear
in command arguments, Terraform state or startup logs.
"""

import json
import os
import sys

for kind in ("LOCATIONS", "CONTACTS"):
    value = os.environ.pop(f"SERVICE_DELIVERY_{kind}_JSON", None)
    if value is None:
        continue
    try:
        json.loads(value)
    except ValueError:
        raise SystemExit("Invalid delivery configuration JSON") from None
    path = f"/tmp/delivery-{kind.lower()}.json"
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w") as output:
        output.write(value)
    os.environ[f"SERVICE_DELIVERY_{kind}_PATH"] = path

os.execvp(sys.argv[1], sys.argv[1:])
