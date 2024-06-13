import json
import logging

import boto3
from test_cnm.tester.cnm_generator import CnmSGeneratorType

log = logging.getLogger(__name__)


class CnmIngestClient:
    def __init__(
        self,
        session: boto3.Session,
        make_cnm_s: CnmSGeneratorType,
        start_queue: str,
        response_queue: str,
    ):
        self.session = session
        self.make_cnm_s = make_cnm_s
        self.start_queue = start_queue
        self.response_queue = response_queue

        self.client = session.client("sqs")
        self._requests = {}

    def submit_request(
        self,
        collection: str,
        data_version: str,
        name: str,
        files: list
    ):
        cnm_s = self.make_cnm_s(collection, data_version, name, files)
        self._requests[(name, cnm_s["submissionTime"])] = True

        message_body = json.dumps(cnm_s, indent=2)
        log.debug("Sending CNM-S: %s", message_body)

        self.client.send_message(
            QueueUrl=self.start_queue,
            MessageBody=message_body,
        )
        return cnm_s

    def get_responses(self):
        return {
            name: cnm_r
            for name, cnm_r in self.iter_responses()
        }

    def iter_responses(self):
        while self._requests:
            response = self.client.receive_message(
                QueueUrl=self.response_queue,
                WaitTimeSeconds=5,
            )
            for message in response.get("Messages", ()):
                cnm_r = json.loads(message["Body"])
                name = cnm_r["identifier"]
                request = self._requests.pop((name, cnm_r["submissionTime"]), None)
                if request is None:
                    continue

                log.debug("Received CNM-R: %s", message["Body"])

                self.client.delete_message(
                    QueueUrl=self.response_queue,
                    ReceiptHandle=message["ReceiptHandle"]
                )

                yield name, cnm_r
