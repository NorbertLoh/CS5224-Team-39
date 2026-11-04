"""Coturn bootstrap/readiness/health for the managed EC2 Auto Scaling fleet.

Only runs on an AWS relay host. Unit tests inject clients and never call AWS.
"""

import ipaddress
import json
import os
from pathlib import Path
import re
import socket
import struct
import sys
import time
from urllib.request import Request, urlopen

COOKIE = 0x2112A442


def metadata(path):
    request = Request(
        "http://169.254.169.254/latest/api/token",
        method="PUT",
        headers={"X-aws-ec2-metadata-token-ttl-seconds": "60"},
    )
    with urlopen(request, timeout=3) as response:
        token = response.read().decode()
    request = Request(
        "http://169.254.169.254/latest/meta-data/" + path,
        headers={"X-aws-ec2-metadata-token": token},
    )
    with urlopen(request, timeout=3) as response:
        return response.read().decode()


def claim_address(client, allocations, instance_id):
    """Never steal an address or re-associate an address already held by this host."""
    addresses = client.describe_addresses(AllocationIds=allocations)["Addresses"]
    for address in addresses:
        if address.get("InstanceId") == instance_id:
            return address["PublicIp"]
    for address in addresses:
        if address.get("AssociationId"):
            continue
        try:
            client.associate_address(
                AllocationId=address["AllocationId"],
                InstanceId=instance_id,
                AllowReassociation=False,
            )
            return address["PublicIp"]
        except Exception as error:
            # Another launching host may claim the same free address first.
            if getattr(error, "response", {}).get("Error", {}).get("Code") != "Resource.AlreadyAssociated":
                raise
    raise RuntimeError("No free TURN address; retry after the old host terminates")


def configuration(secret, realm, public_ip, private_ip):
    if not isinstance(secret, str) or len(secret.encode()) < 32 or "\n" in secret or "\r" in secret:
        raise ValueError("Invalid TURN shared secret")
    if not re.fullmatch(r"[A-Za-z0-9.-]+", realm):
        raise ValueError("Invalid TURN realm")
    if any(ipaddress.ip_address(value).version != 4 for value in (public_ip, private_ip)):
        raise ValueError("TURN requires IPv4 address mapping")
    return "\n".join([
        "listening-port=3478", "fingerprint", "use-auth-secret",
        "static-auth-secret=" + secret, "realm=" + realm,
        "external-ip=" + public_ip + "/" + private_ip,
        "min-port=49160", "max-port=49200", "no-cli", "no-tls", "no-dtls",
        "no-multicast-peers", "user-quota=2", "total-quota=10",
        "max-bps=1000000", "bps-capacity=2500000", "log-file=stdout",
        "denied-peer-ip=0.0.0.0-0.255.255.255",
        "denied-peer-ip=10.0.0.0-10.255.255.255",
        "denied-peer-ip=127.0.0.0-127.255.255.255",
        "denied-peer-ip=169.254.0.0-169.254.255.255",
        "denied-peer-ip=172.16.0.0-172.31.255.255",
        "denied-peer-ip=192.168.0.0-192.168.255.255", "",
    ])


def valid_response(packet, transaction):
    if len(packet) < 20:
        return False
    kind, length, cookie, received = struct.unpack("!HHI12s", packet[:20])
    return kind == 0x0101 and length % 4 == 0 and len(packet) == length + 20 and cookie == COOKIE and received == transaction


def probe():
    for _ in range(3):
        transaction = os.urandom(12)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as connection:
            connection.settimeout(2)
            try:
                connection.sendto(struct.pack("!HHI12s", 1, 0, COOKIE, transaction), ("127.0.0.1", 3478))
                packet, sender = connection.recvfrom(4096)
                if sender == ("127.0.0.1", 3478) and valid_response(packet, transaction):
                    return True
            except OSError:
                continue
    return False


def report_health(client, instance_id, config, healthy, failures):
    entries = client.describe_auto_scaling_instances(InstanceIds=[instance_id])["AutoScalingInstances"]
    if len(entries) != 1 or entries[0]["AutoScalingGroupName"] != config["group"]:
        raise RuntimeError("Instance does not belong to the configured TURN fleet")
    state = entries[0]["LifecycleState"]
    if healthy and state == "Pending:Wait":
        client.complete_lifecycle_action(
            AutoScalingGroupName=config["group"], LifecycleHookName=config["hook"],
            InstanceId=instance_id, LifecycleActionResult="CONTINUE",
        )
    elif not healthy and failures >= 3 and state == "InService":
        client.set_instance_health(
            InstanceId=instance_id, HealthStatus="Unhealthy", ShouldRespectGracePeriod=True,
        )


def main():
    import boto3
    from botocore.config import Config

    config = json.loads(Path("/etc/telelink/turn.json").read_text())
    aws_options = {"region_name": config["region"], "config": Config(connect_timeout=3, read_timeout=5, retries={"max_attempts": 3})}
    instance_id = metadata("instance-id")
    mode = sys.argv[1]
    if mode == "configure":
        address = claim_address(boto3.client("ec2", **aws_options), config["allocations"], instance_id)
        secret = json.loads(boto3.client("secretsmanager", **aws_options).get_secret_value(SecretId=config["secret_arn"])["SecretString"])["shared_secret"]
        content = configuration(secret, config["realm"], address, metadata("local-ipv4"))
        fd = os.open("/etc/turnserver.conf", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as output:
            output.write(content)
        return
    if mode not in {"ready", "health"}:
        raise ValueError("Unknown TURN agent operation")
    healthy = probe()
    if mode == "ready":
        for _ in range(9):
            if healthy:
                break
            time.sleep(2)
            healthy = probe()
    counter = Path("/run/telelink-turn-failures")
    failures = 0 if healthy else (int(counter.read_text()) if counter.exists() else 0) + 1
    counter.write_text(str(failures))
    report_health(boto3.client("autoscaling", **aws_options), instance_id, config, healthy, failures)
    if not healthy:
        raise RuntimeError("TURN protocol probe failed")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # Never emit configuration/credentials in journal output.
        print("TURN bootstrap/readiness/health operation failed", file=sys.stderr)
        sys.exit(1)
