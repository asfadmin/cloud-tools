import functools
from unittest import mock

import boto3
import moto
import pytest
from destroy_cumulus import (
    CumulusDestroyer,
    ElasticsearchDomain,
    Resource,
    SQSQueue,
    main
)


@functools.lru_cache
def get_client(*args, **kwargs):
    return boto3.client(*args, **kwargs)


def test_main_error():
    with pytest.raises(SystemExit):
        main()


@pytest.mark.slow
def test_destroy_all_empty_prefixs(monkeypatch):
    # Patch out unsupported types
    monkeypatch.setitem(Resource.TYPES, "es:domain", mock.create_autospec(ElasticsearchDomain))
    # Mock all is very slow. Using it as a decorator causes the slowness to
    # affect pytest collection time.
    with moto.mock_all():
        destroyer = CumulusDestroyer(profile=None, prefix="", auto_confirm=False)
        destroyer.destroy = mock.create_autospec(destroyer.destroy)

        destroyer.destroy_all()

    destroyer.destroy.assert_called_once()


@moto.mock_sqs
def test_gather_queues():
    client = get_client("sqs")
    client.create_queue(QueueName="test-queue")
    client.create_queue(QueueName="red-herring")

    resources = SQSQueue.gather(get_client, "test")

    assert len(resources) == 1
    queue = resources[0]

    assert queue.name == "test-queue"
    assert queue.id == "test-queue"
