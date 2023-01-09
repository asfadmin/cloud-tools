from unittest import mock

import moto
import pytest
from destroy_cumulus import (
    CumulusDestroyer,
    ElasticsearchDomain,
    Resource,
    SQSQueue
)


@pytest.fixture
def mock_queues(get_client):
    with moto.mock_sqs():
        client = get_client("sqs")
        q1 = client.create_queue(QueueName="test-queue")
        q2 = client.create_queue(QueueName="red-herring")
        yield q1, q2


@pytest.mark.slow
def test_gather_all_empty_prefixs(monkeypatch):
    # Patch out unsupported types
    monkeypatch.setitem(Resource.TYPES, "es:domain", mock.create_autospec(ElasticsearchDomain))
    # Mock all is very slow. Using it as a decorator causes the slowness to
    # affect pytest collection time.
    with moto.mock_all():
        destroyer = CumulusDestroyer(profile=None, prefix="")
        resources = destroyer.gather()

    assert len(resources) == 1


@moto.mock_resourcegroupstaggingapi
def test_gather_filter_queues(mock_queues):
    destroyer = CumulusDestroyer(
        profile=None,
        prefix="test",
        type_filters=["sqs"]
    )
    resources = destroyer.gather()

    assert len(resources) == 1
    queue = next(iter(resources))

    assert queue.name == "test-queue"
    assert queue.id == "test-queue"


def test_gather_queues(get_client, mock_queues):
    resources = SQSQueue.gather(get_client, "test")

    assert len(resources) == 1
    queue = resources[0]

    assert queue.name == "test-queue"
    assert queue.id == "test-queue"
