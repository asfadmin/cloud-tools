import json
import textwrap

import pytest
from test_cnm.main import main


@pytest.fixture(autouse=True)
def test_bucket(test_bucket):
    obj1 = test_bucket.Object("COLLECTION_1/PRODUCT_1/file1.txt")
    obj1.put(Body=b"text1")

    obj2 = test_bucket.Object("COLLECTION_1/PRODUCT_2/file1.txt")
    obj2.put(Body=b"text2")

    obj3 = test_bucket.Object("COLLECTION_2/PRODUCT_2/file1.txt")
    obj3.put(Body=b"text3")

    metadata = test_bucket.Object("metadata.json")
    metadata.put(
        Body=json.dumps(
            {
                "$testconfig": {
                    "COLLECTION_1/PRODUCT_1": {
                        "cnm_ingest_queue": "test-ingest-queue",
                    },
                    "COLLECTION_2/PRODUCT_2": {
                        "cnm_ingest_queue": "test-ingest-queue",
                        "cnm_response_queue": "test-ingest-queue-response",
                    },
                },
            }
        ).encode(),
    )

    return test_bucket


def test_print_config(capcli):
    main(["configure"])

    assert capcli.getvalue() == textwrap.dedent(
        """
    Using config: ConfigBasic(test_bucket='test-bucket', profile=None)
    Collecting tests from bucket test-bucket
    Loading metadata file from s3://test-bucket/metadata.json
    COLLECTION_1/PRODUCT_1:
        cnm_ingest_queue: test-ingest-queue
    COLLECTION_2/PRODUCT_2:
        cnm_ingest_queue: test-ingest-queue
        cnm_response_queue: test-ingest-queue-response
    No changes to metadata file. Skipping save()
    """.lstrip("\n")
    )


def test_set_config(capcli, test_bucket):
    main(
        [
            "configure",
            "COLLECTION_1",
            "--cnm-response-queue",
            "test-c2-response-queue",
        ]
    )

    assert capcli.getvalue() == textwrap.dedent(
        """
    Using config: ConfigBasic(test_bucket='test-bucket', profile=None)
    Collecting tests from bucket test-bucket
    Loading metadata file from s3://test-bucket/metadata.json
    COLLECTION_1/PRODUCT_1 setting cnm_response_queue to test-c2-response-queue
    COLLECTION_1/PRODUCT_1:
        cnm_ingest_queue: test-ingest-queue
        cnm_response_queue: test-c2-response-queue
    COLLECTION_1/PRODUCT_2 setting cnm_response_queue to test-c2-response-queue
    COLLECTION_1/PRODUCT_2:
        cnm_response_queue: test-c2-response-queue
    Saving metadata file to s3://test-bucket/metadata.json
    """.lstrip("\n")
    )

    metadata_obj = test_bucket.Object("metadata.json")
    metadata_dict = json.loads(metadata_obj.get()["Body"].read())

    assert metadata_dict == {
        "$testconfig": {
            "COLLECTION_1/PRODUCT_1": {
                "cnm_ingest_queue": "test-ingest-queue",
                "cnm_response_queue": "test-c2-response-queue",
            },
            "COLLECTION_1/PRODUCT_2": {
                "cnm_response_queue": "test-c2-response-queue",
            },
            "COLLECTION_2/PRODUCT_2": {
                "cnm_ingest_queue": "test-ingest-queue",
                "cnm_response_queue": "test-ingest-queue-response",
            },
        },
    }


def test_set_config_implicit_all(capcli):
    with pytest.raises(SystemExit):
        main(
            [
                "configure",
                "--cnm-response-queue",
                "test-c2-response-queue",
            ]
        )

    assert capcli.getvalue() == textwrap.dedent(
        """
    Using config: ConfigBasic(test_bucket='test-bucket', profile=None)
    No tests selected! If you would like to select all tests, please filter by '*'.
    """.lstrip("\n")
    )
