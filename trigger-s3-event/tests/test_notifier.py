from unittest import mock

from trigger_s3_event.template import FormatValue

from .conftest import DummyNotifier


def test_batched_notify(mock_notifier):
    mock_notifier.batched_notify(
        event_name="s3:ObjectCreated:Put",
        record_template={"key": FormatValue('entry["Key"]')},
        entry={"Key": "entry_1"},
    )
    mock_notifier.send_batch.assert_not_called()

    for i in range(2, 10):
        mock_notifier.batched_notify(
            event_name="s3:ObjectCreated:Put",
            record_template={"key": FormatValue('entry["Key"]')},
            entry={"Key": f"entry_{i}"},
        )
        mock_notifier.send_batch.assert_not_called()

    mock_notifier.batched_notify(
        event_name="s3:ObjectCreated:Put",
        record_template={"key": FormatValue('entry["Key"]')},
        entry={"Key": "entry_10"},
    )

    assert mock_notifier.send_batch.call_args == mock.call(
        [{"key": f"entry_{i}"} for i in range(1, 11)],
    )


def test_passes_event():
    notifier = DummyNotifier(
        client=mock.Mock(),
        configuration={
            "Id": "mock-configuration-id",
            "Events": ["s3:ObjectCreated:*"],
            "Filter": {},
        },
    )

    assert notifier.passes_event("s3:ObjectCreated:Put")
    assert notifier.passes_event("s3:ObjectCreated:Post")
    assert notifier.passes_event("s3:ObjectCreated:Copy")
    assert notifier.passes_event("s3:ObjectCreated:CompleteMultipartUpload")

    assert not notifier.passes_event("s3:ObjectRemoved:Delete")
    assert not notifier.passes_event("s3:ObjectRestore:Post")


def test_passes_filter_rules():
    notifier = DummyNotifier(
        client=mock.Mock(),
        configuration={
            "Id": "mock-configuration-id",
            "Events": ["s3:ObjectCreated:*"],
            "Filter": {
                "Key": {
                    "FilterRules": [
                        {
                            "Name": "prefix",
                            "Value": "foo",
                        },
                        {
                            "Name": "suffix",
                            "Value": "bar",
                        },
                    ],
                },
            },
        },
    )

    assert notifier.passes_filter_rules({"Key": "foobar"})
    assert notifier.passes_filter_rules({"Key": "foo-bar"})
    assert notifier.passes_filter_rules({"Key": "foo-anything-bar"})

    assert not notifier.passes_filter_rules({"Key": "foo"})
    assert not notifier.passes_filter_rules({"Key": "bar"})
    assert not notifier.passes_filter_rules({"Key": "fobar"})
    assert not notifier.passes_filter_rules({"Key": "fooar"})
    assert not notifier.passes_filter_rules({"Key": "something"})
