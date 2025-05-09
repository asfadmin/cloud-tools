import json

import pytest
from test_cnm.main import main


@pytest.fixture(autouse=True)
def test_bucket(test_bucket):
    obj1 = test_bucket.Object("COLLECTION_1/PRODUCT_1/file1.txt")
    obj1.put(Body=b"")

    metadata = test_bucket.Object("metadata.json")
    metadata.put(Body=json.dumps({
        obj1.key: {
            "checksum": "11111111111111111111111111111111",
            "type": "data",
        },
    }).encode())

    return test_bucket


def test_move_file(test_bucket):
    main(["move", "COLLECTION_1/PRODUCT_1/", "COLLECTION_FINAL/PRODUCT_1/"])

    metadata_obj = test_bucket.Object("metadata.json")
    metadata_dict = json.loads(metadata_obj.get()["Body"].read())

    assert "COLLECTION_1/PRODUCT_1/file1.txt" not in metadata_dict
    assert metadata_dict["COLLECTION_FINAL/PRODUCT_1/file1.txt"] == {
        "checksum": "11111111111111111111111111111111",
        "type": "data",
    }
