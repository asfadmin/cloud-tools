from unittest import mock

import moto
import pytest
from destroy_cumulus import (
    CumulusDestroyer,
    EventSourceMapping,
    NameMatcher,
    Resource,
    SQSQueue,
)


@pytest.fixture
def mock_queues(get_client):
    client = get_client("sqs")
    q1 = client.create_queue(QueueName="test-queue")
    q2 = client.create_queue(QueueName="red-herring")
    yield q1, q2


@pytest.mark.slow
def test_gather_all_empty_prefix(monkeypatch):
    # Patch out unsupported types
    # TODO(reweeden): This worked at some point. When can we re-enable it?
    monkeypatch.setitem(Resource.TYPES, "lambda:event-source-mapping", mock.create_autospec(EventSourceMapping))
    # Mock all is very slow. Using it as a decorator causes the slowness to
    # affect pytest collection time.
    with moto.mock_aws():
        destroyer = CumulusDestroyer(
            profile=None,
            name_matcher=NameMatcher(prefix=""),
        )
        resources = destroyer.gather()

    assert len(resources) == 2


def test_gather_filter_queues(mock_queues):
    destroyer = CumulusDestroyer(
        profile=None,
        name_matcher=NameMatcher(prefix="test"),
        type_filters=["sqs"],
    )
    resources = destroyer.gather()

    assert len(resources) == 1
    queue = next(iter(resources))

    assert queue.name == "test-queue"
    assert queue.id == "test-queue"


def test_gather_queues(get_client, mock_queues):
    resources = SQSQueue.gather(get_client, NameMatcher(prefix="test"), {})

    assert len(resources) == 1
    queue = resources[0]

    assert queue.name == "test-queue"
    assert queue.id == "test-queue"
