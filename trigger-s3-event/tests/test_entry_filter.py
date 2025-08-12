from datetime import datetime, timezone

from trigger_s3_event.entry_filter import EntryFilter


def _make_event(
    key,
    last_modified=None,
    etag='"00000000000000000000000000000000"',
    size=0,
    storage_class="STANDARD",
):
    if last_modified is None:
        last_modified = datetime.now(timezone.utc)

    # Message structure including field order from:
    # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3/client/list_objects_v2.html
    event = {
        "Key": key,
        "LastModified": last_modified,
        "ETag": etag,
        "ChecksumAlgorithm": None,
        "Size": size,
        "StorageClass": storage_class,
        "Owner": None,
        "RestoreStatus": None,
    }

    return {
        # ruff hint
        k: v
        for k, v in event.items()
        if v is not None
    }


def test_entry_filter_default():
    entry_filter = EntryFilter()

    # Everything should pass
    assert entry_filter.passes(_make_event("foo"))
    assert entry_filter.passes(_make_event("bar"))
    assert entry_filter.passes(_make_event("/"))
    assert entry_filter.passes(_make_event("foo/bar/baz.txt"))


def test_entry_filter_prefix_after():
    entry_filter = EntryFilter(prefix_after="foo")

    # Normal prefix behavior
    assert entry_filter.passes(_make_event("foo"))
    assert entry_filter.passes(_make_event("foobar"))
    assert entry_filter.passes(_make_event("foo/bar/baz.txt"))

    # Lexicographically later keys
    assert entry_filter.passes(_make_event("goo"))
    assert entry_filter.passes(_make_event("goobar"))
    assert entry_filter.passes(_make_event("zoo/bar/baz.txt"))

    # Lexicographically earlier keys
    assert entry_filter.passes(_make_event("a")) is False
    assert entry_filter.passes(_make_event("afoo")) is False
    assert entry_filter.passes(_make_event("bar")) is False
    assert entry_filter.passes(_make_event("/")) is False


def test_entry_filter_modified_date_range_begin():
    entry_filter = EntryFilter(
        modified_date_range=(
            datetime(2020, 1, 1, tzinfo=timezone.utc),
            None,
        ),
    )

    assert entry_filter.passes(
        _make_event("foo", datetime(2020, 1, 2, tzinfo=timezone.utc)),
    )
    assert entry_filter.passes(
        _make_event("foo", datetime(3000, 1, 1, tzinfo=timezone.utc)),
    )
    # Current date
    assert entry_filter.passes(
        _make_event("foo", datetime.now(timezone.utc)),
    )

    assert (
        entry_filter.passes(
            _make_event("foo", datetime(2000, 1, 1, tzinfo=timezone.utc)),
        )
        is False
    )


def test_entry_filter_modified_date_range_end():
    entry_filter = EntryFilter(
        modified_date_range=(
            None,
            datetime(2020, 1, 1, tzinfo=timezone.utc),
        ),
    )

    assert entry_filter.passes(
        _make_event("foo", datetime(2019, 12, 31, tzinfo=timezone.utc)),
    )
    assert entry_filter.passes(
        _make_event("foo", datetime(1980, 1, 1, tzinfo=timezone.utc)),
    )

    assert (
        entry_filter.passes(
            _make_event("foo", datetime(2024, 1, 1, tzinfo=timezone.utc)),
        )
        is False
    )
    # Current date
    assert (
        entry_filter.passes(
            _make_event("foo", datetime.now(timezone.utc)),
        )
        is False
    )


def test_entry_filter_modified_date_range():
    entry_filter = EntryFilter(
        modified_date_range=(
            datetime(2020, 1, 1, tzinfo=timezone.utc),
            datetime(2022, 1, 1, tzinfo=timezone.utc),
        ),
    )

    assert entry_filter.passes(
        _make_event("foo", datetime(2021, 1, 1, tzinfo=timezone.utc)),
    )

    assert (
        entry_filter.passes(
            _make_event("foo", datetime(1980, 1, 1, tzinfo=timezone.utc)),
        )
        is False
    )
    assert (
        entry_filter.passes(
            _make_event("foo", datetime(2024, 1, 1, tzinfo=timezone.utc)),
        )
        is False
    )
