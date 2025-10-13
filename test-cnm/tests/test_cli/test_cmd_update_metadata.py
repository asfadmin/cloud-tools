import json

import pytest
from test_cnm.main import main


@pytest.fixture(autouse=True)
def test_bucket(test_bucket):
    obj1 = test_bucket.Object("COLLECTION_1/PRODUCT_1/file1.txt")
    obj1.put(Body=b"text1")

    obj2 = test_bucket.Object("COLLECTION_1/PRODUCT_1/file2.txt")
    obj2.put(Body=b"text2")

    obj3 = test_bucket.Object("COLLECTION_1/PRODUCT_1/file3.txt")
    obj3.put(Body=b"text3")

    metadata = test_bucket.Object("metadata.json")
    metadata.put(
        Body=json.dumps(
            {
                obj1.key: {
                    "checksum": "11111111111111111111111111111111",
                },
                obj2.key: {
                    "checksum": "22222222222222222222222222222222",
                },
            }
        ).encode(),
    )

    return test_bucket


@pytest.fixture
def cnm():
    return {
        "identifier": "PRODUCT_1",
        "collection": "COLLECTION_1",
        "version": "1.3",
        "submissionTime": "",
        "product": {
            "name": "PRODUCT_1",
            "dataVersion": "1.0",
            "files": [
                {
                    "name": "file1.txt",
                    "type": "data",
                    "uri": "s3://source-bucket/foobar/file1.txt",
                    "size": 10,
                    "checksum": "from_cnm111111111111111111111111",
                    "checksumType": "md5",
                },
                {
                    "name": "file2.txt",
                    "type": "metadata",
                    "uri": "s3://source-bucket/foobar/file2.txt",
                    "size": 10,
                    "checksum": "from_cnm222222222222222222222222",
                    "checksumType": "md5",
                },
                {
                    "name": "file3.txt",
                    "type": "qa",
                    "uri": "s3://source-bucket/foobar/file3.txt",
                    "size": 10,
                    "checksum": "from_cnm333333333333333333333333",
                    "checksumType": "md5",
                },
            ],
        },
        "provider": "TEST",
    }


def test_update_checksums(test_bucket):
    main(["update-metadata"])

    metadata_obj = test_bucket.Object("metadata.json")
    metadata_dict = json.loads(metadata_obj.get()["Body"].read())

    assert metadata_dict == {
        "COLLECTION_1/PRODUCT_1/file1.txt": {
            "checksum": "cef7ccd89dacf1ced6f5ec91d759953f",
        },
        "COLLECTION_1/PRODUCT_1/file2.txt": {
            "checksum": "fe6123a759017e4a2af4a2d19961ed71",
        },
        "COLLECTION_1/PRODUCT_1/file3.txt": {
            "checksum": "265246eadd25390e2406a0d9bd22242b",
        },
    }


def test_update_from_cnm(test_bucket, tmp_path, cnm):
    cnm_path = tmp_path / "cnm.json"
    with open(cnm_path, "w") as f:
        json.dump(cnm, f)

    main(["update-metadata", "--cnm-file", str(cnm_path)])

    metadata_obj = test_bucket.Object("metadata.json")
    metadata_dict = json.loads(metadata_obj.get()["Body"].read())

    assert metadata_dict == {
        "COLLECTION_1/PRODUCT_1/file1.txt": {
            "checksum": "from_cnm111111111111111111111111",
            "type": "data",
        },
        "COLLECTION_1/PRODUCT_1/file2.txt": {
            "checksum": "from_cnm222222222222222222222222",
            "type": "metadata",
        },
        "COLLECTION_1/PRODUCT_1/file3.txt": {
            "checksum": "from_cnm333333333333333333333333",
            "type": "qa",
        },
    }


def test_update_from_cnm_include_checksum(test_bucket, tmp_path, cnm):
    cnm_path = tmp_path / "cnm.json"
    with open(cnm_path, "w") as f:
        json.dump(cnm, f)

    main(
        [
            "update-metadata",
            "--cnm-file",
            str(cnm_path),
            "--include-property",
            "checksum",
        ]
    )

    metadata_obj = test_bucket.Object("metadata.json")
    metadata_dict = json.loads(metadata_obj.get()["Body"].read())

    assert metadata_dict == {
        "COLLECTION_1/PRODUCT_1/file1.txt": {
            "checksum": "from_cnm111111111111111111111111",
        },
        "COLLECTION_1/PRODUCT_1/file2.txt": {
            "checksum": "from_cnm222222222222222222222222",
        },
        "COLLECTION_1/PRODUCT_1/file3.txt": {
            "checksum": "from_cnm333333333333333333333333",
        },
    }


def test_update_from_cnm_exclude_checksum(test_bucket, tmp_path, cnm):
    cnm_path = tmp_path / "cnm.json"
    with open(cnm_path, "w") as f:
        json.dump(cnm, f)

    main(
        [
            "update-metadata",
            "--cnm-file",
            str(cnm_path),
            "--exclude-property",
            "checksum",
        ]
    )

    metadata_obj = test_bucket.Object("metadata.json")
    metadata_dict = json.loads(metadata_obj.get()["Body"].read())

    assert metadata_dict == {
        "COLLECTION_1/PRODUCT_1/file1.txt": {
            "checksum": "11111111111111111111111111111111",
            "type": "data",
        },
        "COLLECTION_1/PRODUCT_1/file2.txt": {
            "checksum": "22222222222222222222222222222222",
            "type": "metadata",
        },
        "COLLECTION_1/PRODUCT_1/file3.txt": {
            "type": "qa",
        },
    }
