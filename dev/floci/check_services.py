"""F16 service checks for the isolated local emulator. Synthetic data only."""

import argparse
import json
import os
from functools import cache
from pathlib import Path
from urllib.parse import urlsplit
from uuid import uuid4

import boto3
import httpx
from botocore.config import Config

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / ".local/f16-state.json"
ENDPOINT = os.environ.get("F16_ENDPOINT", "http://localhost:4567")
target = urlsplit(ENDPOINT)
if (target.hostname, target.port) not in {
    ("localhost", 4567), ("127.0.0.1", 4567), ("floci", 4566)
}:
    raise SystemExit("Use the isolated emulator on port 4567, or floci:4566 inside its network.")
BUCKET = "telelink-local-documents"
KEY = "f16/persistence.txt"
MARKER = "F16 synthetic persistence marker"
CONSUMERS = ("scheduling", "fulfilment", "document", "notification")
EMAIL = "f16@example.test"


@cache
def aws(service):
    return boto3.client(
        service, endpoint_url=ENDPOINT, region_name="ap-southeast-1",
        aws_access_key_id="test", aws_secret_access_key="test",
        config=Config(connect_timeout=3, read_timeout=5, retries={"max_attempts": 1},
                      s3={"addressing_style": "path"}),
    )


def queue_url(name):
    url = aws("sqs").get_queue_url(QueueName=name)["QueueUrl"]
    return ENDPOINT + urlsplit(url).path


def prepare():
    aws("s3").put_object(Bucket=BUCKET, Key=KEY, Body=MARKER.encode())
    sqs = aws("sqs")
    sqs.create_queue(QueueName="telelink-f16-probe")
    url = queue_url("telelink-f16-probe")
    # Exercise acknowledgement/visibility without deleting the persistence marker.
    sqs.send_message(QueueUrl=url, MessageBody="F16 acknowledge check")
    message = sqs.receive_message(QueueUrl=url, WaitTimeSeconds=2)["Messages"][0]
    assert message["Body"] == "F16 acknowledge check"
    sqs.change_message_visibility(QueueUrl=url, ReceiptHandle=message["ReceiptHandle"],
                                  VisibilityTimeout=0)
    message = sqs.receive_message(QueueUrl=url, WaitTimeSeconds=2)["Messages"][0]
    sqs.delete_message(QueueUrl=url, ReceiptHandle=message["ReceiptHandle"])
    sqs.send_message(QueueUrl=url, MessageBody=MARKER)
    sqs.send_message(QueueUrl=queue_url("telelink-local-scheduling-dlq"), MessageBody=MARKER)

    events = json.loads((ROOT / "contracts/examples/workflow-events.json").read_text())
    result = aws("events").put_events(Entries=events)
    assert result["FailedEntryCount"] == 0, "EventBridge publication failed"

    ses = aws("ses")
    ses.verify_email_identity(EmailAddress=EMAIL)
    ses.send_email(Source=EMAIL, Destination={"ToAddresses": [EMAIL]}, Message={
        "Subject": {"Data": "F16 persistence"}, "Body": {"Text": {"Data": MARKER}},
    })
    BASELINE.parent.mkdir(exist_ok=True)
    BASELINE.write_text(json.dumps(snapshot(), indent=2, sort_keys=True), encoding="utf-8")
    check_messages()
    print("Prepared and verified S3, secrets, queues, routes, SES and Cognito baseline.")


def snapshot():
    s3 = aws("s3")
    object_body = s3.get_object(Bucket=BUCKET, Key=KEY)["Body"].read().decode()
    assert object_body == MARKER
    signed_url = s3.generate_presigned_url("get_object", Params={"Bucket": BUCKET, "Key": KEY})
    assert httpx.get(signed_url).text == MARKER, "Signed download failed"
    public_access = s3.get_public_access_block(Bucket=BUCKET)["PublicAccessBlockConfiguration"]
    assert all(public_access.values()), "Bucket public access block is not enabled"
    state = {"s3": {
        "body": object_body,
        "public_access_block": public_access,
    }}
    state["secrets"] = {}
    for name in ("telelink/local/stripe", "telelink/local/lalamove"):
        secret = aws("secretsmanager").get_secret_value(SecretId=name)
        state["secrets"][name] = {"value": secret["SecretString"], "version": secret["VersionId"]}

    state["sqs"] = {}
    queues = [f"telelink-local-{name}{suffix}" for name in CONSUMERS for suffix in ("", "-dlq")]
    queues += ["telelink-local-event-delivery-dlq", "telelink-f16-probe"]
    attributes = ("QueueArn", "Policy", "RedrivePolicy", "RedriveAllowPolicy",
                  "MessageRetentionPeriod", "VisibilityTimeout")
    for name in queues:
        values = aws("sqs").get_queue_attributes(QueueUrl=queue_url(name), AttributeNames=["All"])
        state["sqs"][name] = {
            key: value for key, value in values["Attributes"].items() if key in attributes
        }

    events = aws("events")
    state["events"] = {"bus": events.describe_event_bus(Name="telelink-local")["Arn"]}
    for name in CONSUMERS:
        rule = name + "-events"
        details = events.describe_rule(Name=rule, EventBusName="telelink-local")
        targets = events.list_targets_by_rule(Rule=rule, EventBusName="telelink-local")["Targets"]
        state["events"][rule] = {
            "arn": details["Arn"], "state": details["State"],
            "pattern": json.loads(details["EventPattern"]),
            "targets": targets,
        }

    cognito = aws("cognito-idp")
    pool = next(pool for pool in cognito.list_user_pools(MaxResults=60)["UserPools"]
                if pool["Name"] == "telelink-local")
    pool_id = pool["Id"]
    clients = cognito.list_user_pool_clients(UserPoolId=pool_id)["UserPoolClients"]
    client = next(client for client in clients
                  if client["ClientName"] == "telelink-web")
    settings = cognito.describe_user_pool_client(
        UserPoolId=pool_id, ClientId=client["ClientId"]
    )["UserPoolClient"]
    assert not settings.get("ClientSecret"), "SPA client must be public"
    state["cognito"] = {"pool_id": pool_id, "client": {
        key: value for key, value in settings.items()
        if key not in ("CreationDate", "LastModifiedDate")
    }, "users": {}}
    for username in ("patient", "doctor", "clinic", "platform"):
        username += "@example.test"
        user = cognito.admin_get_user(UserPoolId=pool_id, Username=username)
        groups = cognito.admin_list_groups_for_user(UserPoolId=pool_id, Username=username)["Groups"]
        state["cognito"]["users"][username] = {
            "enabled": user["Enabled"], "status": user["UserStatus"],
            "attributes": sorted(user["UserAttributes"], key=lambda item: item["Name"]),
            "groups": sorted(group["GroupName"] for group in groups),
        }
    for path in ("openid-configuration", "jwks.json"):
        response = httpx.get(f"{ENDPOINT}/{pool_id}/.well-known/{path}")
        response.raise_for_status()
        state["cognito"][path] = response.json()

    ses = aws("ses")
    mailbox = httpx.get(ENDPOINT + "/_aws/ses").json()
    assert any(message["Body"]["text_part"] == MARKER for message in mailbox["messages"])
    state["ses"] = {
        "identity": ses.get_identity_verification_attributes(Identities=[EMAIL])[
            "VerificationAttributes"
        ],
        "mailbox": mailbox,
    }
    return state


def check_messages():
    sqs = aws("sqs")
    for name in ("telelink-f16-probe", "telelink-local-scheduling-dlq"):
        messages = sqs.receive_message(QueueUrl=queue_url(name), VisibilityTimeout=0,
                                      WaitTimeSeconds=2, MaxNumberOfMessages=10).get("Messages", [])
        assert any(message["Body"] == MARKER for message in messages), f"Missing marker in {name}"
    routes = {
        "scheduling": {"consultation_payment_succeeded.v1"},
        "fulfilment": {"medication_payment_succeeded.v1"},
        "document": {"prescription_issued.v1", "medical_certificate_issued.v1"},
        "notification": {
            "appointment_confirmed.v1", "document_ready.v1", "delivery_status_changed.v1"
        },
    }
    for name, expected in routes.items():
        messages = sqs.receive_message(
            QueueUrl=queue_url(f"telelink-local-{name}"), VisibilityTimeout=0,
            WaitTimeSeconds=2, MaxNumberOfMessages=10,
        ).get("Messages", [])
        actual = {json.loads(message["Body"])["detail-type"] for message in messages}
        assert actual == expected, f"Missing or unexpected routed events in {name}: {actual}"


def check():
    if not BASELINE.is_file():
        raise SystemExit("Missing baseline. Run check_services.py prepare before restarting Floci.")
    expected = json.loads(BASELINE.read_text(encoding="utf-8"))
    actual = snapshot()
    for service, values in actual.items():
        assert values == expected[service], f"{service} state changed after restart"
        print(f"{service}: persisted state matches")
    check_messages()
    print("Pending SQS/DLQ messages and all routed events survived.")


def exercise():
    """Prove restored resources still accept new writes, sends and event routing."""
    s3 = aws("s3")
    s3.put_object(Bucket=BUCKET, Key="f16/after-recreation.txt", Body=MARKER.encode())
    body = s3.get_object(Bucket=BUCKET, Key="f16/after-recreation.txt")["Body"].read()
    assert body == MARKER.encode()
    secrets = aws("secretsmanager")
    secrets.create_secret(Name="telelink/f16-probe", SecretString="synthetic-v1")
    secrets.put_secret_value(SecretId="telelink/f16-probe", SecretString="synthetic-v2")
    assert secrets.get_secret_value(SecretId="telelink/f16-probe")["SecretString"] == "synthetic-v2"
    ses = aws("ses")
    ses.send_email(Source=EMAIL, Destination={"ToAddresses": [EMAIL]}, Message={
        "Subject": {"Data": "F16 after recreation"}, "Body": {"Text": {"Data": MARKER}},
    })
    mailbox = httpx.get(ENDPOINT + "/_aws/ses").json()["messages"]
    assert any(message["Subject"] == "F16 after recreation" for message in mailbox)

    events = json.loads((ROOT / "contracts/examples/workflow-events.json").read_text())
    run_id = str(uuid4())
    expected = {}
    for event in events:
        detail = json.loads(event["Detail"])
        detail.update(event_id=str(uuid4()), correlation_id=run_id)
        event["Detail"] = json.dumps(detail)
        expected[event["DetailType"]] = detail
    assert aws("events").put_events(Entries=events)["FailedEntryCount"] == 0
    received = {}
    for consumer in CONSUMERS:
        messages = aws("sqs").receive_message(
            QueueUrl=queue_url(f"telelink-local-{consumer}"), MaxNumberOfMessages=10,
            WaitTimeSeconds=2, VisibilityTimeout=0,
        ).get("Messages", [])
        for message in messages:
            body = json.loads(message["Body"])
            if body["detail"]["correlation_id"] == run_id:
                received[body["detail-type"]] = body["detail"]
    assert received == expected, "Restored rules did not deliver all new event payloads"
    print("Post-recreation writes, secret versions, SES capture and fresh event routes passed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("prepare", "check", "exercise"))
    args = parser.parse_args()
    if args.action == "prepare":
        prepare()
    elif args.action == "check":
        check()
    else:
        exercise()
