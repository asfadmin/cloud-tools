import json

import pytest
from test_cnm.main import main


@pytest.fixture(autouse=True)
def test_bucket(test_bucket):
    obj1 = test_bucket.Object("COLLECTION_1/")
    obj1.put(Body=b"")
    obj2 = test_bucket.Object("COLLECTION_1/PRODUCT_1/")
    obj2.put(Body=b"")
    obj3 = test_bucket.Object("COLLECTION_1/PRODUCT_1/file1.txt")
    obj3.put(Body=b"text1")
    obj4 = test_bucket.Object("COLLECTION_1/PRODUCT_1/file2.txt")
    obj4.put(Body=b"text2")

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
                obj3.key: {
                    "checksum": "33333333333333333333333333333333",
                    "type": "data",
                },
                obj4.key: {
                    "checksum": "44444444444444444444444444444444",
                    "type": "qa",
                },
                "some-extra-key": {
                    "checksum": "55555555555555555555555555555555",
                    "type": "metadata",
                },
            }
        ).encode()
    )

    return test_bucket


def test_tidy(test_bucket):
    main(["tidy"])

    assert [obj.key for obj in test_bucket.objects.all()] == [
        "COLLECTION_1/PRODUCT_1/file1.txt",
        "COLLECTION_1/PRODUCT_1/file2.txt",
        "metadata.json",
    ]
    metadata_obj = test_bucket.Object("metadata.json")
    metadata_dict = json.loads(metadata_obj.get()["Body"].read())

    assert metadata_dict == {
        "COLLECTION_1/PRODUCT_1/file1.txt": {
            "checksum": "33333333333333333333333333333333",
            "type": "data",
        },
        "COLLECTION_1/PRODUCT_1/file2.txt": {
            "checksum": "44444444444444444444444444444444",
            "type": "qa",
        },
    }


def test_tidy_keep_metadata(test_bucket):
    main(["tidy", "--keep-metadata"])

    assert [obj.key for obj in test_bucket.objects.all()] == [
        "COLLECTION_1/PRODUCT_1/file1.txt",
        "COLLECTION_1/PRODUCT_1/file2.txt",
        "metadata.json",
    ]
    metadata_obj = test_bucket.Object("metadata.json")
    metadata_dict = json.loads(metadata_obj.get()["Body"].read())

    assert metadata_dict == {
        "COLLECTION_1/": {
            "checksum": "11111111111111111111111111111111",
        },
        "COLLECTION_1/PRODUCT_1/": {
            "checksum": "22222222222222222222222222222222",
        },
        "COLLECTION_1/PRODUCT_1/file1.txt": {
            "checksum": "33333333333333333333333333333333",
            "type": "data",
        },
        "COLLECTION_1/PRODUCT_1/file2.txt": {
            "checksum": "44444444444444444444444444444444",
            "type": "qa",
        },
        "some-extra-key": {
            "checksum": "55555555555555555555555555555555",
            "type": "metadata",
        },
    }
