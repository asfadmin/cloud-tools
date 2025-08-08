import pytest
from destroy_cumulus import Arn, CloudWatchEventRule


@pytest.fixture
def client_events(get_client):
    yield get_client("events")


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
                "Arn": (
                    "arn:aws:lambda:us-west-2:123456789012:"
                    "function:lambda-function-name"
                ),
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
                "Arn": (
                    "arn:aws:lambda:us-west-2:123456789012:"
                    f"function:lambda-function-name{i}"
                ),
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
