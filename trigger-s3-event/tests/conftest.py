import logging
import os
from unittest import mock

import boto3
import pytest
from moto import mock_aws
from trigger_s3_event.notifier import Notifier

logging.getLogger("trigger_s3_event").setLevel(logging.DEBUG)
logging.getLogger("botocore").setLevel(logging.WARNING)
logging.getLogger("boto3").setLevel(logging.WARNING)


class DummyNotifier(Notifier):
    def send_batch(self, batch):
        pass


@pytest.fixture(scope="session", autouse=True)
def aws_credentials():
    """Mocked AWS Credentials for moto."""
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"


@pytest.fixture
def boto_session():
    with mock_aws():
        yield boto3.Session()


@pytest.fixture
def s3_resource():
    with mock_aws():
        yield boto3.resource("s3")


@pytest.fixture
def mock_notifier():
    notifier = DummyNotifier(
        client=mock.Mock(),
        configuration={
            "Id": "mock-configuration-id",
            "Events": ["s3:ObjectCreated:*"],
            "Filter": {},
        },
    )
    notifier.send_batch = mock.Mock(Notifier.send_batch)

    return notifier
