import contextlib

import pytest
from destroy_cumulus import Arn, Bucket, CloudWatchEventRule


@pytest.fixture
def client_events(get_client):
    yield get_client("events")


@pytest.fixture
def client_s3(get_client):
    yield get_client("s3")


@pytest.fixture
def test_bucket(s3_resource):
    bucket_name = "test-bucket"

    bucket = s3_resource.Bucket(bucket_name)
    bucket.create()
    bucket.Versioning().enable()

    foo = bucket.Object("foo.txt")
    bar = bucket.Object("bar.txt")
    foo.put(Body=b"foo")
    bar.put(Body=b"bar")
    # create a new version of foo.txt
    foo.put(Body=b"foo 2")
    # Create a delete marker for bar.txt
    bar.delete()

    yield bucket

    with contextlib.suppress(s3_resource.meta.client.exceptions.NoSuchBucket):
        bucket.object_versions.delete()
        bucket.delete()


def test_delete_bucket(get_client, test_bucket):
    bucket = Bucket.from_arn(Arn(f"arn:aws:s3:::{test_bucket.name}"))
    bucket.delete(get_client)


def test_delete_rule_targets(get_client, client_events):
    rule_arn = client_events.put_rule(
        Name="test-rule",
        ScheduleExpression="rate(5 minutes)",
    )["RuleArn"]

    client_events.put_targets(
        Rule="test-rule",
        Targets=[
            {
                "Id": "target1",
                "Arn": "arn:aws:lambda:us-west-2:123456789012:function:lambda-function-name",
            }
        ],
    )

    rule = CloudWatchEventRule.from_arn(Arn(rule_arn))
    rule.delete(get_client)


def test_delete_rule_many_targets(get_client, client_events):
    rule_arn = client_events.put_rule(
        Name="test-rule",
        ScheduleExpression="rate(5 minutes)",
    )["RuleArn"]

    client_events.put_targets(
        Rule="test-rule",
        Targets=[
            {
                "Id": f"target{i}",
                "Arn": f"arn:aws:lambda:us-west-2:123456789012:function:lambda-function-name{i}",
            }
            for i in range(3000)
        ],
    )

    rule = CloudWatchEventRule.from_arn(Arn(rule_arn))
    rule.delete(get_client)


def test_delete_rule_no_targets(get_client, client_events):
    rule_arn = client_events.put_rule(
        Name="test-rule-no-targets",
        ScheduleExpression="rate(5 minutes)",
    )["RuleArn"]

    rule = CloudWatchEventRule.from_arn(Arn(rule_arn))
    rule.delete(get_client)
