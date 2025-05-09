import textwrap

import pytest
from test_cnm.main import main


@pytest.fixture(autouse=True)
def test_bucket(test_bucket):
    test_bucket.Object("COLLECTION_1/PRODUCT_1/file1.txt").put(Body=b"")
    test_bucket.Object("COLLECTION_1/PRODUCT_1/file2.txt").put(Body=b"")
    test_bucket.Object("COLLECTION_1/PRODUCT_2/file1.txt").put(Body=b"")
    test_bucket.Object("COLLECTION_1/PRODUCT_2/file2.txt").put(Body=b"")

    test_bucket.Object(
        "COLLECTION_2/VERY/NESTED/STRUCTURE/PRODUCT_1/file1.txt",
    ).put(Body=b"")
    test_bucket.Object(
        "COLLECTION_2/VERY/NESTED/STRUCTURE/PRODUCT_1/file2.txt",
    ).put(Body=b"")
    test_bucket.Object(
        "COLLECTION_2/SOME/NESTED/STRUCTURE/PRODUCT_1/file3.txt",
    ).put(Body=b"")
    test_bucket.Object(
        "COLLECTION_2/ANOTHER/DIFFERENT/NESTED/STRUCTURE/PRODUCT_1/file4.txt",
    ).put(Body=b"")

    test_bucket.Object("DATA_VERSION_1/1.0/PRODUCT_1/file1.txt").put(Body=b"")
    test_bucket.Object("DATA_VERSION_1/1.0/PRODUCT_1/file2.txt").put(Body=b"")

    test_bucket.Object("DATA_VERSION_2/1/PRODUCT_1/file1.txt").put(Body=b"")
    test_bucket.Object("DATA_VERSION_2/1/PRODUCT_1/file2.txt").put(Body=b"")

    test_bucket.Object("OTHER_COLLECTION/PRODUCT_1/file1.txt").put(Body=b"")
    test_bucket.Object("OTHER_COLLECTION/PRODUCT_1/file2.txt").put(Body=b"")

    return test_bucket


def test_list_all(capcli):
    main(["list"])

    assert capcli.getvalue() == textwrap.dedent("""
    Using config: ConfigBasic(test_bucket='test-bucket', profile=None)
    Collecting tests from bucket test-bucket
    COLLECTION_1:
      - PRODUCT_1 (2 files)
      - PRODUCT_2 (2 files)
    COLLECTION_2:
      - PRODUCT_1 (4 files)
    DATA_VERSION_1:
      - 1.0/PRODUCT_1 (2 files)
    DATA_VERSION_2:
      - 1/PRODUCT_1 (2 files)
    OTHER_COLLECTION:
      - PRODUCT_1 (2 files)

    Totals: 5 Collections; 6 Tests
    """.lstrip("\n"))


def test_list_prefix(capcli):
    main(["list", "COLLECTION_1"])

    assert capcli.getvalue() == textwrap.dedent("""
    Using config: ConfigBasic(test_bucket='test-bucket', profile=None)
    Collecting tests from bucket test-bucket
    COLLECTION_1:
      - PRODUCT_1 (2 files)
      - PRODUCT_2 (2 files)

    Totals: 1 Collections; 2 Tests
    """.lstrip("\n"))


def test_list_prefix_multiple(capcli):
    main(["list", "COLLECTION_1", "COLLECTION_2"])

    assert capcli.getvalue() == textwrap.dedent("""
    Using config: ConfigBasic(test_bucket='test-bucket', profile=None)
    Collecting tests from bucket test-bucket
    COLLECTION_1:
      - PRODUCT_1 (2 files)
      - PRODUCT_2 (2 files)
    COLLECTION_2:
      - PRODUCT_1 (4 files)

    Totals: 2 Collections; 3 Tests
    """.lstrip("\n"))


def test_list_files(capcli):
    main(["list", "--files"])

    assert capcli.getvalue() == textwrap.dedent("""
    Using config: ConfigBasic(test_bucket='test-bucket', profile=None)
    Collecting tests from bucket test-bucket
    COLLECTION_1:
      - PRODUCT_1 (2 files)
        ├── file1.txt
        └── file2.txt
      - PRODUCT_2 (2 files)
        ├── file1.txt
        └── file2.txt
    COLLECTION_2:
      - PRODUCT_1 (4 files)
        ├── file1.txt
        ├── file2.txt
        ├── file3.txt
        └── file4.txt
    DATA_VERSION_1:
      - 1.0/PRODUCT_1 (2 files)
        ├── file1.txt
        └── file2.txt
    DATA_VERSION_2:
      - 1/PRODUCT_1 (2 files)
        ├── file1.txt
        └── file2.txt
    OTHER_COLLECTION:
      - PRODUCT_1 (2 files)
        ├── file1.txt
        └── file2.txt

    Totals: 5 Collections; 6 Tests
    """.lstrip("\n"))
