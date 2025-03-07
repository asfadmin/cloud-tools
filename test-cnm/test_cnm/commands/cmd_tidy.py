import argparse
import logging

from test_cnm.checksums import Checksums
from test_cnm.config import ConfigBasic

log = logging.getLogger(__name__)


def add_parser(
    subparsers: argparse._SubParsersAction,
) -> argparse.ArgumentParser:
    parser_tidy = subparsers.add_parser(
        "tidy",
        help=(
            "Tidy the test bucket by removing 0 byte 'folders' created by "
            "the AWS console and removing checksums for keys that no longer "
            "exist"
        ),
    )
    parser_tidy.add_argument(
        "--keep-checksums",
        help=(
            "Don't remove checksums for objects that are missing from the test "
            "bucket"
        ),
        action="store_true",
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

    with Checksums(session, config.test_bucket) as checksums:
        extra_checksums = dict(checksums.checksums)

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

                del extra_checksums[key]

        extra_key_count = len(extra_checksums)
        if not args.keep_checksums:
            for key in extra_checksums:
                log.info("Removing checksums for %s", key)
                del checksums[key]

    log.info("Totals: %s deleted out of %s objects", deleted, total)
    if args.keep_checksums:
        log.info(
            "Totals: %s extra keys found in checksums.json",
            extra_key_count,
        )
    else:
        log.info(
            "Totals: %s keys pruned from checksums.json",
            extra_key_count,
        )
