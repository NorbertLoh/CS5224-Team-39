"""Protocol/ownership/readiness tests; no host changes, sockets or AWS calls."""

import importlib.util
from pathlib import Path
import struct
import unittest
from unittest.mock import Mock

spec = importlib.util.spec_from_file_location("turn_agent", Path(__file__).parents[1] / "turn_agent.py")
agent = importlib.util.module_from_spec(spec)
spec.loader.exec_module(agent)


class AwsError(Exception):
    def __init__(self, code):
        self.response = {"Error": {"Code": code}}


class TurnAgentTests(unittest.TestCase):
    def test_owned_address_is_not_remapped_or_charged_again(self):
        client = Mock()
        client.describe_addresses.return_value = {"Addresses": [{"InstanceId": "i-self", "PublicIp": "203.0.113.1", "AssociationId": "a"}]}
        self.assertEqual(agent.claim_address(client, ["pool"], "i-self"), "203.0.113.1")
        client.associate_address.assert_not_called()

    def test_never_steals_another_live_hosts_address(self):
        client = Mock()
        client.describe_addresses.return_value = {"Addresses": [{"InstanceId": "i-other", "PublicIp": "203.0.113.1", "AssociationId": "a"}]}
        with self.assertRaises(RuntimeError):
            agent.claim_address(client, ["pool"], "i-self")
        client.associate_address.assert_not_called()

    def test_claim_race_moves_to_next_slot_with_reassociation_disabled(self):
        client = Mock()
        client.describe_addresses.return_value = {"Addresses": [
            {"AllocationId": "slot-1", "PublicIp": "203.0.113.1"},
            {"AllocationId": "slot-2", "PublicIp": "203.0.113.2"},
        ]}
        client.associate_address.side_effect = [AwsError("Resource.AlreadyAssociated"), {}]
        self.assertEqual(agent.claim_address(client, ["slot-1", "slot-2"], "i-self"), "203.0.113.2")
        for call in client.associate_address.call_args_list:
            self.assertFalse(call.kwargs["AllowReassociation"])

    def test_permission_or_uncertain_association_failure_is_not_hidden(self):
        client = Mock()
        client.describe_addresses.return_value = {"Addresses": [{"AllocationId": "slot-1", "PublicIp": "203.0.113.1"}]}
        client.associate_address.side_effect = AwsError("UnauthorizedOperation")
        with self.assertRaises(AwsError):
            agent.claim_address(client, ["slot-1"], "i-self")

    def test_stun_requires_matching_transaction_cookie_type_and_length(self):
        transaction = b"abcdefghijkl"
        packet = struct.pack("!HHI12s", 0x0101, 0, agent.COOKIE, transaction)
        self.assertTrue(agent.valid_response(packet, transaction))
        for invalid in [packet[:10], packet + b"x", struct.pack("!HHI12s", 0x0111, 0, agent.COOKIE, transaction), struct.pack("!HHI12s", 0x0101, 0, 0, transaction)]:
            self.assertFalse(agent.valid_response(invalid, transaction))
        self.assertFalse(agent.valid_response(packet, b"other-id-123"))

    def test_config_preserves_auth_external_mapping_and_private_peer_denials(self):
        value = agent.configuration("x" * 32, "signal.example.org", "203.0.113.1", "10.39.0.4")
        self.assertIn("use-auth-secret\n", value)
        self.assertIn("external-ip=203.0.113.1/10.39.0.4\n", value)
        self.assertIn("denied-peer-ip=169.254.0.0-169.254.255.255", value)
        self.assertIn("denied-peer-ip=10.0.0.0-10.255.255.255", value)
        with self.assertRaises(ValueError):
            agent.configuration("x" * 32 + "\nno-auth", "signal.example.org", "203.0.113.1", "10.39.0.4")

    def test_healthy_pending_instance_completes_launch_only_after_probe(self):
        client = self.asg("Pending:Wait")
        agent.report_health(client, "i-self", {"group": "fleet", "hook": "ready"}, True, 0)
        self.assertEqual(client.complete_lifecycle_action.call_args.kwargs["LifecycleActionResult"], "CONTINUE")
        client.set_instance_health.assert_not_called()

    def test_startup_failure_does_not_bypass_abandon_hook(self):
        client = self.asg("Pending:Wait")
        agent.report_health(client, "i-self", {"group": "fleet", "hook": "ready"}, False, 3)
        client.complete_lifecycle_action.assert_not_called()
        client.set_instance_health.assert_not_called()

    def test_three_failed_checks_replace_only_inservice_instance_respecting_grace(self):
        client = self.asg("InService")
        agent.report_health(client, "i-self", {"group": "fleet", "hook": "ready"}, False, 2)
        client.set_instance_health.assert_not_called()
        agent.report_health(client, "i-self", {"group": "fleet", "hook": "ready"}, False, 3)
        self.assertTrue(client.set_instance_health.call_args.kwargs["ShouldRespectGracePeriod"])
        self.assertEqual(client.set_instance_health.call_args.kwargs["InstanceId"], "i-self")

    def test_agent_cannot_signal_an_unrelated_fleet(self):
        client = self.asg("InService")
        with self.assertRaises(RuntimeError):
            agent.report_health(client, "i-self", {"group": "different", "hook": "ready"}, False, 3)
        client.set_instance_health.assert_not_called()

    @staticmethod
    def asg(state):
        client = Mock()
        client.describe_auto_scaling_instances.return_value = {"AutoScalingInstances": [{"AutoScalingGroupName": "fleet", "LifecycleState": state}]}
        return client


if __name__ == "__main__":
    unittest.main()
