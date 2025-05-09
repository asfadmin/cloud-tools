import logging
import os
from pathlib import Path

import boto3
import pytest
from moto import mock_aws

logging.getLogger("test_cnm").setLevel(logging.DEBUG)
logging.getLogger("botocore").setLevel(logging.WARNING)
logging.getLogger("boto3").setLevel(logging.WARNING)


@pytest.fixture(scope="session")
def data_path():
    return Path(__file__).parent / "data"


@pytest.fixture(scope="session", autouse=True)
def aws_credentials():
    """Mocked AWS Credentials for moto."""
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["AWS_DEFAULT_REGION"] = "us-east-1"


@pytest.fixture(scope="session")
def get_client():
    return boto3.client


@pytest.fixture
def s3_resource():
    with mock_aws():
        yield boto3.resource("s3")


@pytest.fixture
def sqs_client():
    with mock_aws():
        yield boto3.client("sqs")
