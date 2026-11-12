"""Local reset job tests never connect to a running local or AWS environment."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch
from uuid import uuid4

import local_reset_worker as worker
from telelink_common.file_jobs import FileJobs
from test_aws_reset import Connection


class LocalResetTests(unittest.TestCase):
    def test_floci_localhost_urls_are_normalized_to_the_container(self):
        sqs = Mock()
        sqs.get_paginator.return_value.paginate.return_value = [
            {"QueueUrls": ["http://localhost:4566/000000000000/telelink-local-test"]}
        ]
        sqs.get_queue_attributes.return_value = {"Attributes": {"ApproximateNumberOfMessages": "0"}}
        with patch.object(worker.time, "sleep"):
            worker.clear_queues(sqs)
        self.assertEqual(
            sqs.purge_queue.call_args.kwargs["QueueUrl"],
            "http://floci:4566/000000000000/telelink-local-test",
        )

    def test_queue_urls_cannot_select_remote_targets(self):
        sqs = Mock()
        sqs.get_paginator.return_value.paginate.return_value = [
            {"QueueUrls": ["https://sqs.ap-southeast-1.amazonaws.com/123/telelink-local-test"]}
        ]
        with self.assertRaises(ValueError):
            worker.clear_queues(sqs)
        sqs.purge_queue.assert_not_called()

    def test_preflight_rejects_nonlocal_configuration_before_mutation(self):
        with (
            patch.object(worker, "local_settings", side_effect=ValueError("nonlocal")),
            patch.object(worker, "context") as context,
            self.assertRaises(ValueError),
        ):
            worker.preflight()
        context.assert_not_called()

    def run_job(self, failure=None):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        jobs = FileJobs(Path(temporary.name))
        state = {"request_id": str(uuid4()), "actor_id": str(uuid4())}
        connection = Connection()
        cognito = Mock()
        sqs = Mock()
        with (
            patch.object(
                worker,
                "preflight",
                return_value=({}, "+6581234567", "TestPassword1!", cognito, "pool"),
            ),
            patch.object(worker, "admin", return_value=connection),
            patch.object(worker.boto3, "client", return_value=sqs) as aws,
            patch.object(worker, "seed_users", return_value={}),
            patch.object(worker.time, "sleep"),
            patch.object(worker, "clear_queues"),
            patch.object(worker, "clear_cache"),
            patch.object(worker, "seed_database", side_effect=failure),
        ):
            if failure:
                with self.assertRaises(ValueError):
                    worker.run(jobs, state)
            else:
                worker.run(jobs, state)
            assert aws.call_args.kwargs["endpoint_url"] == "http://floci:4566"
            assert aws.call_args.kwargs["aws_access_key_id"] == "test"
        self.assertEqual(sum(" LOGIN" in q for q in connection.queries), 9)
        return connection, jobs.read()

    def test_local_job_restores_all_logins_and_finishes(self):
        _, state = self.run_job()
        self.assertEqual(state["status"], "succeeded")
        self.assertFalse(state["roles_quiesced"])

    def test_failed_seed_restores_logins_and_rolls_back(self):
        connection, state = self.run_job(ValueError("seed failed"))
        self.assertEqual(connection.rollbacks, 1)
        self.assertFalse(state["roles_quiesced"])
        self.assertNotEqual(state["status"], "succeeded")


if __name__ == "__main__":
    unittest.main()
