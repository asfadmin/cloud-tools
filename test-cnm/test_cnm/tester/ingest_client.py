import json
import logging
from collections.abc import Generator
from typing import Optional

import boto3
from test_cnm.tester.cnm_generator import CnmSGeneratorType
from test_cnm.tester.types import ExecutableTest

log = logging.getLogger(__name__)


class CnmIngestClient:
    def __init__(
        self,
        session: boto3.Session,
        make_cnm_s: CnmSGeneratorType,
        cnm_response_queue: str,
    ):
        self.session = session
        self.make_cnm_s = make_cnm_s
        self.cnm_response_queue = cnm_response_queue

        self.client = session.client("sqs")
        self._requests = {}

    @property
    def is_waiting(self) -> bool:
        return bool(self._requests)

    def submit_request(self, test: ExecutableTest) -> dict:
        assert test.cnm_response_queue == self.cnm_response_queue

        cnm_s = self.make_cnm_s(
            test.collection,
            test.resolved_data_version,
            test.name,
            test.files,
            test.provider,
            test.trace,
        )

        message_body = json.dumps(cnm_s, indent=2)
        log.debug("Sending CNM-S to %s: %s", test.cnm_ingest_queue, message_body)

        self.client.send_message(
            QueueUrl=test.cnm_ingest_queue,
            MessageBody=message_body,
        )

        key = (cnm_s["identifier"], cnm_s["submissionTime"])
        if key in self._requests:
            log.warning("CNM-S identifier conflicts with in-flight request %s", key)
        self._requests[key] = True

        return cnm_s

    def iter_responses(self) -> Generator[dict]:
        while self.is_waiting:
            yield from self.process_messages(wait_time_seconds=5)

    def process_messages(self, wait_time_seconds: Optional[int] = None) -> Generator[dict]:
        if not self.is_waiting:
            return

        response = self._receive_message(wait_time_seconds=wait_time_seconds)

        for message in response.get("Messages", ()):
            cnm_r = json.loads(message["Body"])
            request = self._requests.pop(
                (cnm_r["identifier"], cnm_r["submissionTime"]),
                None,
            )
            if request is None:
                continue

            log.debug(
                "Received CNM-R from %s: %s",
                self.cnm_response_queue,
                message["Body"],
            )

            self.client.delete_message(
                QueueUrl=self.cnm_response_queue,
                ReceiptHandle=message["ReceiptHandle"],
            )

            yield cnm_r

    def _receive_message(self, wait_time_seconds: Optional[int] = None) -> dict:
        if wait_time_seconds is None:
            log.debug("Short polling %s", self.cnm_response_queue)
            return self.client.receive_message(
                QueueUrl=self.cnm_response_queue,
                MaxNumberOfMessages=10,
            )

        log.debug(
            "Long polling %s for %s seconds",
            self.cnm_response_queue,
            wait_time_seconds,
        )
        return self.client.receive_message(
            QueueUrl=self.cnm_response_queue,
            MaxNumberOfMessages=10,
            WaitTimeSeconds=wait_time_seconds,
        )
