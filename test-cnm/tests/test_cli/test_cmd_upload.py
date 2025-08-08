import json

from test_cnm.main import main


def test_upload_file(test_bucket, tmp_path):
    file1 = tmp_path / "file1.txt"
    file1.write_text("text1")

    main(
        [
            "upload",
            "--collection",
            "COLLECTION_1",
            "--product",
            "PRODUCT_1",
            str(file1),
        ]
    )

    assert [obj.key for obj in test_bucket.objects.all()] == [
        "COLLECTION_1/PRODUCT_1/file1.txt",
        "metadata.json",
    ]

    metadata_obj = test_bucket.Object("metadata.json")
    metadata_dict = json.loads(metadata_obj.get()["Body"].read())

    assert metadata_dict == {
        "COLLECTION_1/PRODUCT_1/file1.txt": {
            "checksum": "cef7ccd89dacf1ced6f5ec91d759953f",
        },
    }


def test_upload_file_with_data_version(test_bucket, tmp_path):
    file1 = tmp_path / "file1.txt"
    file1.write_text("text1")

    main(
        [
            "upload",
            "--collection",
            "COLLECTION_1",
            "--product",
            "PRODUCT_1",
            "--data-version",
            "1",
            str(file1),
        ]
    )

    assert [obj.key for obj in test_bucket.objects.all()] == [
        "COLLECTION_1/1/PRODUCT_1/file1.txt",
        "metadata.json",
    ]

    metadata_obj = test_bucket.Object("metadata.json")
    metadata_dict = json.loads(metadata_obj.get()["Body"].read())

    assert metadata_dict == {
        "COLLECTION_1/1/PRODUCT_1/file1.txt": {
            "checksum": "cef7ccd89dacf1ced6f5ec91d759953f",
        },
    }


def test_upload_directory(test_bucket, tmp_path):
    dir_path = tmp_path / "upload"
    dir_path.mkdir()

    (dir_path / "file1.txt").write_text("text1")
    (dir_path / "file2.txt").write_text("text2")
    (dir_path / "file3.txt").write_text("text3")

    main(
        [
            "upload",
            "--collection",
            "COLLECTION_1",
            "--product",
            "PRODUCT_1",
            "--recursive",
            str(dir_path),
        ]
    )

    assert [obj.key for obj in test_bucket.objects.all()] == [
        "COLLECTION_1/PRODUCT_1/file1.txt",
        "COLLECTION_1/PRODUCT_1/file2.txt",
        "COLLECTION_1/PRODUCT_1/file3.txt",
        "metadata.json",
    ]

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
