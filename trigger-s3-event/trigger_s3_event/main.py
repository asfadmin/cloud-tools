import argparse
import json
import logging
import sys
import uuid
from datetime import datetime
from importlib.metadata import Distribution
from platform import python_version
from typing import Optional

import boto3
import dateparser
from trigger_s3_event.entry_filter import EntryFilter
from trigger_s3_event.event_generator import EventGenerator
from trigger_s3_event.notifier import (
    LambdaNotifier,
    Notifier,
    SNSTopicNotifier,
    SQSQueueNotifier,
)

log = logging.getLogger(__name__)

HELP = r"""
This tool sends fake S3 event notifications for objects that already exist in a
bucket. It can use either the existing notification configurations or send
notifications to a destination passed as an argument to the tool.

# Examples

The default is to send a notification for all objects in the bucket to all
notification configurations that exist on the bucket:

  trigger-s3-event --bucket asf-cumulus-dev-alos2-landing

To send notifications for objects in a prefix, starting at a certain point:

  trigger-s3-event \
    --bucket asf-cumulus-dev-alos2-landing \
    --prefix my-prefix/ \
    --prefix-after my-prefix/2020-01

To send notifications for objects with a LastModified date in a time range:

  trigger-s3-event \
    --bucket asf-cumulus-dev-alos2-landing \
    --modified-after "2024-03-26T00:12:18.373139Z" \
    --modified-before "yesterday"
"""


def _get_version() -> str:
    name = "trigger-s3-event"
    dist = Distribution.from_name(name)
    direct_url = json.loads(dist.read_text("direct_url.json"))
    editable = direct_url.get("dir_info", {}).get("editable", False)
    return f"{name} {'(editable) ' if editable else ''}{dist.version} on Python {python_version()}"


def date(text: str) -> datetime:
    return dateparser.parse(
        text,
        settings={"RETURN_AS_TIMEZONE_AWARE": True},
    )


def get_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        epilog=HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("--version", action="version", version=_get_version())
    parser.add_argument("--profile", help="AWS profile to use")
    parser.add_argument(
        "--bucket",
        help="S3 bucket to scan",
        required=True,
    )
    parser.add_argument(
        "--notify",
        help="Override notification configuration and send to this Arn instead",
    )
    parser.add_argument(
        "--dryrun",
        help="Log notifications to the console instead of sending them",
        action="store_true",
    )
    parser.add_argument(
        "--limit",
        help="Limit the number of notifications sent",
        type=int,
    )

    filter_group = parser.add_argument_group(title="filter options")
    filter_group.add_argument(
        "--prefix",
        help="S3 bucket prefix",
        default="",
    )
    filter_group.add_argument(
        "--prefix-after",
        help="Only send keys that come after this prefix lexicographically",
        default="",
    )
    filter_group.add_argument(
        "--modified-after",
        help="Only send objects modified after this date",
        type=date,
    )
    filter_group.add_argument(
        "--modified-before",
        help="Only send objects modified before this date",
        type=date,
    )

    return parser


def main(args: Optional[list[str]] = None):
    parser = get_parser()
    pargs = parser.parse_args(args=args)

    root_logger = logging.getLogger()
    boto3_logger = logging.getLogger("boto3")
    botocore_logger = logging.getLogger("botocore")
    urllib3_logger = logging.getLogger("urllib3")
    s3transfer_logger = logging.getLogger("s3transfer")

    root_logger.setLevel(logging.INFO)
    boto3_logger.setLevel(logging.WARNING)
    botocore_logger.setLevel(logging.WARNING)
    urllib3_logger.setLevel(logging.WARNING)
    s3transfer_logger.setLevel(logging.WARNING)

    root_logger.addHandler(logging.StreamHandler(sys.stdout))

    session = boto3.Session(profile_name=pargs.profile)
    override_notifiers: list[Notifier] = []
    if pargs.notify:
        if ":lambda:" in pargs.notify:
            lambda_client = session.client("lambda")
            override_notifiers.append(
                LambdaNotifier(
                    lambda_client,
                    {
                        "Id": f"trigger-s3-event-override-{uuid.uuid4()}",
                        "Events": ["s3:ObjectCreated:*"],
                        "TopicArn": pargs.notify,
                    },
                    pargs.dryrun,
                ),
            )
        elif ":sns:" in pargs.notify:
            sns_client = session.client("sns")
            override_notifiers.append(
                SNSTopicNotifier(
                    sns_client,
                    {
                        "Id": f"trigger-s3-event-override-{uuid.uuid4()}",
                        "Events": ["s3:ObjectCreated:*"],
                        "TopicArn": pargs.notify,
                    },
                    pargs.dryrun,
                ),
            )
        elif ":sqs:" in pargs.notify:
            sqs_client = session.client("sqs")
            override_notifiers.append(
                SQSQueueNotifier(
                    sqs_client,
                    {
                        # For configuration structure including field order see:
                        # https://boto3.amazonaws.com/v1/documentation/api/latest/reference/services/s3/client/get_bucket_notification_configuration.html
                        "Id": f"trigger-s3-event-override-{uuid.uuid4()}",
                        "Events": ["s3:ObjectCreated:*"],
                        "QueueArn": pargs.notify,
                    },
                    pargs.dryrun,
                ),
            )

        else:
            log.error(
                "--notify: Notification type is not supported for %s",
                pargs.notify,
            )
            raise SystemExit()

    event_generator = EventGenerator(
        session,
        bucket=pargs.bucket,
        dry_run=pargs.dryrun,
        limit=pargs.limit,
    )

    event_generator.send_events(
        prefix=pargs.prefix,
        entry_filter=EntryFilter(
            prefix_after=pargs.prefix_after,
            modified_date_range=(
                pargs.modified_after,
                pargs.modified_before,
            ),
        ),
        override_notifiers=override_notifiers,
    )
