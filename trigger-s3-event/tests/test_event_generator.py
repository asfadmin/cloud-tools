import pytest
from trigger_s3_event.event_generator import EventGenerator


@pytest.fixture
def test_bucket(s3_resource):
    bucket = s3_resource.Bucket("test-bucket")
    bucket.create()

    bucket.Object("foo").put(Body="")
    bucket.Object("bar").put(Body="")
    bucket.Object("baz").put(Body="")

    return bucket


def test_init_static_data(boto_session, test_bucket):
    sqs_client = boto_session.client("sqs")
    sns_client = boto_session.client("sns")

    queue_1 = "test-queue-1"
    sqs_client.create_queue(QueueName=queue_1)
    topic_1 = "topic-1"
    sns_client.create_topic(Name=topic_1)
    topic_2 = "topic-2"
    sns_client.create_topic(Name=topic_2)

    test_bucket.Notification().put(
        NotificationConfiguration={
            "TopicConfigurations": [
                {
                    "Id": "topic-1-config",
                    "TopicArn": f"arn:aws:sns:us-east-1:123456789012:{topic_1}",
                    "Events": ["s3:ObjectCreated:*"],
                },
                {
                    "Id": "topic-2-config",
                    "TopicArn": f"arn:aws:sns:us-east-1:123456789012:{topic_2}",
                    "Events": ["s3:ObjectCreated:*"],
                    "Filter": {
                        "Key": {
                            "FilterRules": [
                                {
                                    "Name": "prefix",
                                    "Value": "foo",
                                },
                            ],
                        },
                    },
                },
            ],
            "QueueConfigurations": [
                {
                    "Id": "queue-1-config",
                    "QueueArn": f"arn:aws:sqs:us-east-1:123456789012:{queue_1}",
                    "Events": ["s3:ObjectCreated:*"],
                },
            ],
        },
    )
    event_generator = EventGenerator(boto_session, test_bucket.name)

    event_generator._init_static_data()

    assert event_generator._user_identity == "AKIAIOSFODNN7EXAMPLE"

    assert len(event_generator._notifiers) == 3
    assert event_generator._notifiers[0].configuration_id == "queue-1-config"
    assert event_generator._notifiers[0].configuration_filter == {}

    assert event_generator._notifiers[1].configuration_id == "topic-1-config"
    assert event_generator._notifiers[1].configuration_filter == {}

    assert event_generator._notifiers[2].configuration_id == "topic-2-config"
    assert event_generator._notifiers[2].configuration_filter == {
        "Key": {
            "FilterRules": [
                {
                    "Name": "prefix",
                    "Value": "foo",
                },
            ],
        },
    }


def test_send_events(boto_session, test_bucket, mock_notifier):
    event_generator = EventGenerator(boto_session, test_bucket.name)

    event_generator.send_events(override_notifiers=[mock_notifier])

    mock_notifier.send_batch.assert_called_once()

    call_args_batch = mock_notifier.send_batch.call_args.args[0]
    event_object_keys = [
        record["s3"]["object"]["key"]
        for event in call_args_batch
        for record in event["Records"]
    ]
    assert event_object_keys == ["bar", "baz", "foo"]
