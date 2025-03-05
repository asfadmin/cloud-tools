import argparse
import logging

from test_cnm.config import ConfigBasic

log = logging.getLogger(__name__)


def add_parser(
    subparsers: argparse._SubParsersAction,
) -> argparse.ArgumentParser:
    parser_tidy = subparsers.add_parser(
        "tidy",
        help=(
            "Tidy the test bucket by removing 0 byte 'folders' created by "
            "the AWS console"
        ),
    )
    parser_tidy.set_defaults(
        func=cmd_tidy,
        config_cls=ConfigBasic,
    )

    return parser_tidy


def cmd_tidy(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
    config: ConfigBasic,
):
    session = config.session()

    client = session.client("s3")
    paginator = client.get_paginator("list_objects_v2")

    total = 0
    deleted = 0
    for response in paginator.paginate(Bucket=config.test_bucket):
        bucket = response["Name"]
        for entry in response.get("Contents", ()):
            total += 1
            key = entry["Key"]

            if entry["Size"] == 0 and key[-1] == "/":
                log.info("Removing s3://%s/%s", bucket, key)
                client.delete_object(
                    Bucket=bucket,
                    Key=key,
                )
                deleted += 1

    log.info("Totals: %s deleted out of %s objects", deleted, total)
