import logging
import os
from pathlib import Path
from typing import Optional

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


@pytest.fixture
def boto_session():
    with mock_aws():
        yield boto3.Session()


@pytest.fixture
def s3_resource(boto_session):
    return boto_session.resource("s3")


@pytest.fixture
def sqs_client(boto_session):
    return boto_session.client("sqs")


@pytest.fixture
def test_bucket(s3_resource):
    bucket = s3_resource.Bucket("test-bucket")
    bucket.create()

    return bucket


@pytest.fixture
def mock_make_cnm_s():
    uid = 0

    def mock_make_cnm_s(
        collection: str,
        data_version: str,
        name: str,
        files: list,
        provider: str,
        trace: Optional[str],
    ) -> dict:
        nonlocal uid
        uid += 1

        return {
            "identifier": str(uid),
            "collection": collection,
            "version": "1.3",
            "submissionTime": "2026-01-01T00:00:00.000Z",
            "product": {
                "name": name,
                "dataVersion": data_version,
                "files": [
                    {
                        "name": Path(file["Key"]).name,
                        "type": "data",
                        "uri": f"s3://{file['Bucket']}/{file['Key']}",
                        "size": file["Size"],
                        "checksum": file["ETag"],
                        "checksumType": "md5",
                    }
                    for file in files
                ],
            },
            "provider": provider,
        }

    return mock_make_cnm_s
