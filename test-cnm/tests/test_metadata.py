import json
from unittest import mock

import pytest
from test_cnm.metadata import Metadata


@pytest.fixture
def metadata(boto_session, test_bucket):
    return Metadata(
        session=boto_session,
        bucket=test_bucket.name,
    )


def test_load(test_bucket, metadata):
    test_bucket.Object("metadata.json").put(
        Body=json.dumps({"foo": {"checksum": "bar"}}),
    )

    metadata.load()

    assert metadata.metadata == {
        "$testconfig": {},
        "foo": {"checksum": "bar"},
    }


def test_save(test_bucket, metadata):
    metadata["foo"]["checksum"] = "baz"
    metadata["bar"]["checksum"] = "qux"

    metadata.save()

    contents = json.load(test_bucket.Object("metadata.json").get()["Body"])
    assert contents == {
        "foo": {
            "checksum": "baz",
        },
        "bar": {
            "checksum": "qux",
        },
    }


def test_save_when_unmodified(test_bucket, metadata):
    test_bucket.Object("metadata.json").put(
        Body=json.dumps({"foo": {"checksum": "bar"}}),
    )

    metadata.load()
    metadata.session = mock.Mock()
    metadata.save()

    metadata.session.client().upload_fileobj.assert_not_called()


def test_contextmanager(test_bucket, metadata):
    test_bucket.Object("metadata.json").put(
        Body=json.dumps({"foo": {"checksum": "bar"}}),
    )

    with metadata:
        assert metadata["foo"] == {"checksum": "bar"}

        metadata["foo"]["checksum"] = "baz"
        metadata["bar"]["checksum"] = "qux"

    contents = json.load(test_bucket.Object("metadata.json").get()["Body"])
    assert contents == {
        "foo": {
            "checksum": "baz",
        },
        "bar": {
            "checksum": "qux",
        },
    }


def test_crud(metadata):
    assert "foo" not in metadata
    metadata["foo"]["bar"] = "baz"
    assert "foo" in metadata
    assert metadata["foo"] == {"bar": "baz"}
    del metadata["foo"]
    assert "foo" not in metadata
