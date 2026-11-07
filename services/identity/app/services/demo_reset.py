"""S3 conditional writes serialize reset requests across API replicas."""

import json
from contextlib import closing
from datetime import datetime, timezone

from telelink_common.errors import DomainError

KEY = "reset/state.json"
TERMINAL = {"succeeded", "failed"}


class ResetControl:
    def __init__(self, config):
        self.config = config

    def client(self, name):
        import boto3
        from botocore.config import Config

        return boto3.client(
            name,
            region_name=self.config["region"],
            config=Config(
                connect_timeout=5, read_timeout=10, retries={"mode": "standard", "max_attempts": 2}
            ),
        )

    def read(self, s3):
        try:
            result = s3.get_object(Bucket=self.config["bucket"], Key=KEY)
        except s3.exceptions.NoSuchKey:
            return None, None
        with closing(result["Body"]) as body:
            return json.loads(body.read()), result["ETag"]

    def status(self):
        with closing(self.client("s3")) as s3:
            state, _ = self.read(s3)
        return self.public(state)

    @staticmethod
    def public(state):
        if state is None:
            return {"status": "ready"}
        return {key: state[key] for key in ("request_id", "status", "stage", "updated_at")}

    def start(self, request_id, actor_id):
        from botocore.exceptions import BotoCoreError, ClientError

        with closing(self.client("s3")) as s3:
            state, etag = self.read(s3)
            if state and state["request_id"] == request_id:
                if state["status"] != "queued":
                    return self.public(state)
                # Retrying an interrupted launch uses ECS's same idempotency token.
            else:
                if state and state["status"] not in TERMINAL:
                    raise DomainError(409, "reset_active", "A demo reset is already running.")
                state = {
                    "request_id": request_id,
                    "actor_id": actor_id,
                    "status": "queued",
                    "stage": "Waiting for reset worker",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
                try:
                    s3.put_object(
                        Bucket=self.config["bucket"],
                        Key=KEY,
                        Body=json.dumps(state).encode(),
                        ContentType="application/json",
                        **({"IfMatch": etag} if etag else {"IfNoneMatch": "*"}),
                    )
                except ClientError as error:
                    if error.response["Error"]["Code"] in {
                        "PreconditionFailed",
                        "ConditionalRequestConflict",
                    }:
                        raise DomainError(
                            409, "reset_active", "Another reset request won the claim."
                        ) from None
                    raise
            try:
                with closing(self.client("ecs")) as ecs:
                    result = ecs.run_task(
                        cluster=self.config["cluster"],
                        taskDefinition=self.config["task"],
                        clientToken=request_id,
                        startedBy=request_id,
                        launchType="FARGATE",
                        platformVersion="1.4.0",
                        networkConfiguration=self.config["network"],
                        overrides={
                            "containerOverrides": [
                                {
                                    "name": "demo-reset",
                                    "environment": [
                                        {"name": "RESET_REQUEST_ID", "value": request_id},
                                    ],
                                }
                            ]
                        },
                    )
                if result.get("failures") or len(result.get("tasks", [])) != 1:
                    raise DomainError(
                        503,
                        "reset_launch_failed",
                        "Reset worker could not start. Retry this request.",
                    )
            except (BotoCoreError, ClientError):
                # Do not release the claim: AWS may have accepted an interrupted request.
                raise DomainError(
                    503,
                    "reset_launch_failed",
                    "Could not confirm reset launch. Retry this request.",
                ) from None
        return self.public(state)
