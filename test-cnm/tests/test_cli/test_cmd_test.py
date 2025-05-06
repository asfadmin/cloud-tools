import configparser
import json
import threading
from datetime import datetime

import pytest
from test_cnm.main import main


@pytest.fixture(autouse=True)
def test_bucket(test_bucket):
    obj1 = test_bucket.Object("COLLECTION_1/PRODUCT_1/file1.txt")
    obj1.put(Body=b"")

    obj2 = test_bucket.Object("COLLECTION_1/PRODUCT_1/file2.txt")
    obj2.put(Body=b"")

    obj3 = test_bucket.Object("COLLECTION_2/PRODUCT_1/file1.txt")
    obj3.put(Body=b"")

    metadata = test_bucket.Object("metadata.json")
    metadata.put(Body=json.dumps({
        obj1.key: {
            "checksum": "11111111111111111111111111111111",
            "type": "data",
        },
        obj1.key: {
            "checksum": "22222222222222222222222222222222",
        },
    }).encode())

    return test_bucket


@pytest.fixture(autouse=True)
def test_cnm_ingest_queue(sqs_client):
    queue_name = "test-cnm-ingest-queue"
    response = sqs_client.create_queue(QueueName=queue_name)
    return queue_name, response["QueueUrl"]


@pytest.fixture(autouse=True)
def test_cnm_response_queue(sqs_client):
    queue_name = "test-cnm-response-queue"
    response = sqs_client.create_queue(QueueName=queue_name)
    return queue_name, response["QueueUrl"]


@pytest.fixture
def cnm_responder(sqs_client, test_cnm_ingest_queue, test_cnm_response_queue):
    """A fixture to listen for CNM-S messages and send fake CNM-R messages to
    the response queue
    """
    return CnmResponder(
        sqs_client,
        test_cnm_ingest_queue[1],
        test_cnm_response_queue[1],
    )


@pytest.fixture(autouse=True)
def current_directory(
    tmp_path,
    monkeypatch,
    test_bucket,
    test_cnm_ingest_queue,
    test_cnm_response_queue,
):
    cwd_path = tmp_path / "cwd"
    cwd_path.mkdir()

    monkeypatch.chdir(str(cwd_path.absolute()))

    config_file = cwd_path / "testcnm.cfg"
    config = configparser.ConfigParser()
    config["default"] = {
        "test_bucket": test_bucket.name,
        "provider": "UNIT-TEST",
        "cnm_ingest_queue": test_cnm_ingest_queue[0],
        "cnm_response_queue": test_cnm_response_queue[0],
        "stack_name": "test",
    }
    with open(config_file, "w") as f:
        config.write(f)

    return cwd_path


class CnmResponder:
    def __init__(
        self,
        sqs_client,
        cnm_ingest_queue_url: str,
        cnm_response_queue_url: str,
    ):
        self.sqs_client = sqs_client
        self.cnm_ingest_queue_url = cnm_ingest_queue_url
        self.cnm_response_queue_url = cnm_response_queue_url
        self.thread = None
        self.is_running = False

    def cnm_response_worker(self):
        while self.is_running:
            response = self.sqs_client.receive_message(
                QueueUrl=self.cnm_ingest_queue_url,
                WaitTimeSeconds=1,
            )
            for message in response.get("Messages", ()):
                cnm_s = json.loads(message["Body"])

                cnm_r = {
                    "version": cnm_s["version"],
                    "receivedTime": cnm_s.get("receivedTime"),
                    "processCompleteTime": datetime.utcnow().strftime(
                        "%Y-%m-%d %H:%M:%SZ",
                    ),
                    "product": {
                        "name": cnm_s["product"]["name"],
                        "files": cnm_s["product"]["files"],
                    },
                    "submissionTime": cnm_s["submissionTime"],
                    "identifier": cnm_s["identifier"],
                    "collection": cnm_s["collection"],
                    "response": {
                        "status": "SUCCESS",
                    },
                    "provider": cnm_s["provider"],
                }

                self.sqs_client.send_message(
                    QueueUrl=self.cnm_response_queue_url,
                    MessageBody=json.dumps(cnm_r),
                )

    def start(self):
        if self.is_running:
            raise RuntimeError("CnmResponder is already running")

        self.is_running = True
        self.thread = threading.Thread(target=self.cnm_response_worker)
        self.thread.start()

    def stop(self):
        self.is_running = False
        if self.thread:
            self.thread.join()
        self.thread = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_val, exc_type, exc_tb):
        self.stop()


def test_test(cnm_responder, caplog):
    with cnm_responder:
        main(["test"])

    assert "Starting: COLLECTION_1/PRODUCT_1" in caplog.text
    assert (
        "Skipping COLLECTION_2/PRODUCT_1 as the product name conflicts with "
        "already started test COLLECTION_1/PRODUCT_1"
    ) in caplog.text
    assert "True\tSUCCESS\t| COLLECTION_1/PRODUCT_1" in caplog.text
    assert "Totals: 1 Succeeded; 0 Failed of 1 tests" in caplog.text
