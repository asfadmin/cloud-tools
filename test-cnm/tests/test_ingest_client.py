import json

import pytest
from test_cnm.tester.ingest_client import CnmIngestClient
from test_cnm.tester.types import ExecutableTest


@pytest.fixture()
def ingest_queue(sqs_client):
    queue_name = "test-cnm-ingest-queue"
    response = sqs_client.create_queue(QueueName=queue_name)
    return queue_name, response["QueueUrl"]


@pytest.fixture()
def response_queue(sqs_client):
    queue_name = "test-cnm-response-queue"
    response = sqs_client.create_queue(QueueName=queue_name)
    return queue_name, response["QueueUrl"]


def test_submit_request(boto_session, sqs_client, mock_make_cnm_s, ingest_queue):
    ingest_client = CnmIngestClient(
        session=boto_session,
        make_cnm_s=mock_make_cnm_s,
        cnm_response_queue="<unused>",
    )

    cnm_s = ingest_client.submit_request(
        ExecutableTest(
            collection="TEST_COLLECTION",
            data_version=None,
            resolved_data_version="1.0",
            name="TEST_1",
            files=[
                {
                    "Bucket": "test",
                    "Key": "TEST_COLLECTION/TEST_1/TEST_1.json",
                    "Size": 100,
                    "ETag": '"foobarbaz"',
                }
            ],
            cnm_ingest_queue=ingest_queue[1],
            cnm_response_queue="<unused>",
            provider="test-provider",
        )
    )

    expected = {
        "identifier": "1",
        "collection": "TEST_COLLECTION",
        "version": "1.3",
        "submissionTime": "2026-01-01T00:00:00.000Z",
        "product": {
            "name": "TEST_1",
            "dataVersion": "1.0",
            "files": [
                {
                    "name": "TEST_1.json",
                    "type": "data",
                    "uri": "s3://test/TEST_COLLECTION/TEST_1/TEST_1.json",
                    "size": 100,
                    "checksum": '"foobarbaz"',
                    "checksumType": "md5",
                }
            ],
        },
        "provider": "test-provider",
    }

    assert cnm_s == expected

    response = sqs_client.receive_message(QueueUrl=ingest_queue[1])
    messages = [json.loads(msg["Body"]) for msg in response.get("Messages", ())]
    assert messages == [expected]


def test_process_messages(boto_session, sqs_client, mock_make_cnm_s, ingest_queue, response_queue):
    ingest_client = CnmIngestClient(
        session=boto_session,
        make_cnm_s=mock_make_cnm_s,
        cnm_response_queue=response_queue[1],
    )

    cnm_s = ingest_client.submit_request(
        ExecutableTest(
            collection="TEST_COLLECTION",
            data_version=None,
            resolved_data_version="1.0",
            name="TEST_1",
            files=[
                {
                    "Bucket": "test",
                    "Key": "TEST_COLLECTION/TEST_1/TEST_1.json",
                    "Size": 100,
                    "ETag": '"foobarbaz"',
                }
            ],
            cnm_ingest_queue=ingest_queue[1],
            cnm_response_queue=response_queue[1],
            provider="test-provider",
        )
    )

    assert list(ingest_client.process_messages()) == []
    assert ingest_client.is_waiting

    sqs_client.send_message(
        QueueUrl=response_queue[1],
        MessageBody=json.dumps(
            {
                "identifier": cnm_s["identifier"],
                "submissionTime": cnm_s["submissionTime"],
                "response": {
                    "status": "SUCCESS",
                },
            }
        ),
    )

    assert list(ingest_client.process_messages()) == [
        {
            "identifier": cnm_s["identifier"],
            "submissionTime": cnm_s["submissionTime"],
            "response": {
                "status": "SUCCESS",
            },
        }
    ]
    assert not ingest_client.is_waiting
