import json
from unittest import mock

import pytest
from test_cnm.config import ConfigFull
from test_cnm.metadata import Metadata
from test_cnm.tester.executor import TestExecutor
from test_cnm.tester.types import ExecutableTest, TestCollector, TestInfo


@pytest.fixture
def executor(boto_session, test_bucket, mock_make_cnm_s, ingest_queue_1, response_queue):
    return TestExecutor(
        session=boto_session,
        collector=mock.create_autospec(TestCollector),
        make_cnm_s=mock_make_cnm_s,
        metadata=Metadata(boto_session, test_bucket.name),
        config=ConfigFull(
            test_bucket=test_bucket.name,
            cnm_ingest_queue=ingest_queue_1[1],
            cnm_response_queue=response_queue[1],
            provider="TEST",
        ),
    )


@pytest.fixture()
def ingest_queue_1(sqs_client):
    queue_name = "test-cnm-ingest-queue-1"
    response = sqs_client.create_queue(QueueName=queue_name)
    return queue_name, response["QueueUrl"]


@pytest.fixture()
def ingest_queue_2(sqs_client):
    queue_name = "test-cnm-ingest-queue-2"
    response = sqs_client.create_queue(QueueName=queue_name)
    return queue_name, response["QueueUrl"]


@pytest.fixture()
def response_queue(sqs_client):
    queue_name = "test-cnm-response-queue"
    response = sqs_client.create_queue(QueueName=queue_name)
    return queue_name, response["QueueUrl"]


def test_collect_tests(executor, ingest_queue_1, response_queue):
    executor.collector.collect_tests.return_value = {
        "TEST_1": TestInfo(
            collection="TEST_COLLECTION",
            data_version="1.0",
            name="TEST_1",
            files=[
                {
                    "Bucket": "test",
                    "Key": "TEST_COLLECTION/TEST_1/TEST_1.json",
                    "Size": 100,
                    "ETag": '"foobarbaz"',
                }
            ],
        ),
        "TEST_2": TestInfo(
            collection="TEST_COLLECTION",
            data_version="1.0",
            name="TEST_2",
            files=[
                {
                    "Bucket": "test",
                    "Key": "TEST_COLLECTION/TEST_2/TEST_2.json",
                    "Size": 100,
                    "ETag": '"foobarbaz"',
                }
            ],
        ),
    }
    test_run = executor.new_test_run([])

    test_run.collect_tests()

    assert test_run.tests == [
        ExecutableTest(
            collection="TEST_COLLECTION",
            data_version="1.0",
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
            cnm_ingest_queue=ingest_queue_1[1],
            cnm_response_queue=response_queue[1],
        ),
        ExecutableTest(
            collection="TEST_COLLECTION",
            data_version="1.0",
            resolved_data_version="1.0",
            name="TEST_2",
            files=[
                {
                    "Bucket": "test",
                    "Key": "TEST_COLLECTION/TEST_2/TEST_2.json",
                    "Size": 100,
                    "ETag": '"foobarbaz"',
                }
            ],
            cnm_ingest_queue=ingest_queue_1[1],
            cnm_response_queue=response_queue[1],
        ),
    ]


def test_iter_start_tests(executor, sqs_client, ingest_queue_1, response_queue):
    test_run = executor.new_test_run([])

    test_run.tests = [
        ExecutableTest(
            collection="TEST_COLLECTION",
            data_version="1.0",
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
            cnm_ingest_queue=ingest_queue_1[1],
            cnm_response_queue=response_queue[1],
        ),
        ExecutableTest(
            collection="TEST_COLLECTION",
            data_version="1.0",
            resolved_data_version="1.0",
            name="TEST_2",
            files=[
                {
                    "Bucket": "test",
                    "Key": "TEST_COLLECTION/TEST_2/TEST_2.json",
                    "Size": 100,
                    "ETag": '"foobarbaz"',
                }
            ],
            cnm_ingest_queue=ingest_queue_1[1],
            cnm_response_queue=response_queue[1],
        ),
    ]
    test_run._state = "tests_collected"

    for _ in test_run.iter_start_tests():
        pass

    assert len(test_run.pending_tests) == 2
    assert test_run.num_started == 2

    response = sqs_client.receive_message(QueueUrl=ingest_queue_1[1], MaxNumberOfMessages=10)
    messages = [json.loads(msg["Body"]) for msg in response.get("Messages", ())]
    assert messages == [
        {
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
        },
        {
            "identifier": "2",
            "collection": "TEST_COLLECTION",
            "version": "1.3",
            "submissionTime": "2026-01-01T00:00:00.000Z",
            "product": {
                "name": "TEST_2",
                "dataVersion": "1.0",
                "files": [
                    {
                        "name": "TEST_2.json",
                        "type": "data",
                        "uri": "s3://test/TEST_COLLECTION/TEST_2/TEST_2.json",
                        "size": 100,
                        "checksum": '"foobarbaz"',
                        "checksumType": "md5",
                    }
                ],
            },
            "provider": "test-provider",
        },
    ]


def test_iter_start_tests_multiple_clients(
    executor,
    sqs_client,
    ingest_queue_1,
    ingest_queue_2,
    response_queue,
):
    test_run = executor.new_test_run([])

    test_run.tests = [
        ExecutableTest(
            collection="TEST_COLLECTION",
            data_version="1.0",
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
            cnm_ingest_queue=ingest_queue_1[1],
            cnm_response_queue=response_queue[1],
        ),
        ExecutableTest(
            collection="TEST_COLLECTION",
            data_version="1.0",
            resolved_data_version="1.0",
            name="TEST_2",
            files=[
                {
                    "Bucket": "test",
                    "Key": "TEST_COLLECTION/TEST_2/TEST_2.json",
                    "Size": 100,
                    "ETag": '"foobarbaz"',
                }
            ],
            cnm_ingest_queue=ingest_queue_2[1],
            cnm_response_queue=response_queue[1],
        ),
    ]
    test_run._state = "tests_collected"

    for _ in test_run.iter_start_tests():
        pass

    assert len(test_run.pending_tests) == 2
    assert test_run.num_started == 2

    response = sqs_client.receive_message(QueueUrl=ingest_queue_1[1], MaxNumberOfMessages=10)
    messages = [json.loads(msg["Body"]) for msg in response.get("Messages", ())]
    assert messages == [
        {
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
        },
    ]

    response = sqs_client.receive_message(QueueUrl=ingest_queue_2[1], MaxNumberOfMessages=10)
    messages = [json.loads(msg["Body"]) for msg in response.get("Messages", ())]
    assert messages == [
        {
            "identifier": "2",
            "collection": "TEST_COLLECTION",
            "version": "1.3",
            "submissionTime": "2026-01-01T00:00:00.000Z",
            "product": {
                "name": "TEST_2",
                "dataVersion": "1.0",
                "files": [
                    {
                        "name": "TEST_2.json",
                        "type": "data",
                        "uri": "s3://test/TEST_COLLECTION/TEST_2/TEST_2.json",
                        "size": 100,
                        "checksum": '"foobarbaz"',
                        "checksumType": "md5",
                    }
                ],
            },
            "provider": "test-provider",
        },
    ]


def test_iter_responses(
    executor,
    sqs_client,
    ingest_queue_1,
    ingest_queue_2,
    response_queue,
):
    test_run = executor.new_test_run([])

    test_run.tests = [
        ExecutableTest(
            collection="TEST_COLLECTION",
            data_version="1.0",
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
            cnm_ingest_queue=ingest_queue_1[1],
            cnm_response_queue=response_queue[1],
        ),
        ExecutableTest(
            collection="TEST_COLLECTION",
            data_version="1.0",
            resolved_data_version="1.0",
            name="TEST_2",
            files=[
                {
                    "Bucket": "test",
                    "Key": "TEST_COLLECTION/TEST_2/TEST_2.json",
                    "Size": 100,
                    "ETag": '"foobarbaz"',
                }
            ],
            cnm_ingest_queue=ingest_queue_2[1],
            cnm_response_queue=response_queue[1],
        ),
    ]
    test_run._state = "tests_collected"

    for _ in test_run.iter_start_tests():
        pass

    sqs_client.send_message(
        QueueUrl=response_queue[1],
        MessageBody=json.dumps(
            {
                "identifier": "1",
                "submissionTime": "2026-01-01T00:00:00.000Z",
                "response": {
                    "status": "SUCCESS",
                },
            }
        ),
    )
    sqs_client.send_message(
        QueueUrl=response_queue[1],
        MessageBody=json.dumps(
            {
                "identifier": "2",
                "submissionTime": "2026-01-01T00:00:00.000Z",
                "response": {
                    "status": "FAILURE",
                },
            }
        ),
    )

    _ = list(test_run.iter_responses())
    assert test_run.num_succeeded == 1
    assert test_run.num_failed == 1
    assert not test_run.pending_tests
