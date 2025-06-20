"""
A script for triggering ingest for event based ingest systems.

Run with --help for more information.
"""

import argparse
import logging
import sys
from typing import Optional

from .commands import cmd_test

log = logging.getLogger(__name__)


def get_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--verbose",
        "-v",
        help="Increase verbosity level. Can be passed multiple times.",
        action="count",
        default=0,
    )
    parser.add_argument(
        "--profile",
        help="AWS profile name",
        default=None,
    )
    parser.add_argument(
        "--test-bucket",
        help="S3 bucket containing E2E test data",
    )

    subparsers = parser.add_subparsers(
        title="commands",
        required=True,
        dest="command",
    )
    cmd_test.add_parser(subparsers)

    return parser


def main(args: Optional[list[str]] = None):
    parser = get_parser()
    pargs = parser.parse_args(args=args)

    root_logger = logging.getLogger()
    boto3_logger = logging.getLogger("boto3")
    botocore_logger = logging.getLogger("botocore")
    s3transfer_logger = logging.getLogger("s3transfer")

    root_logger.setLevel(logging.INFO)
    boto3_logger.setLevel(logging.WARNING)
    botocore_logger.setLevel(logging.WARNING)
    s3transfer_logger.setLevel(logging.WARNING)

    if pargs.verbose >= 1:
        root_logger.setLevel(logging.DEBUG)
    if pargs.verbose >= 2:
        boto3_logger.setLevel(logging.DEBUG)
        botocore_logger.setLevel(logging.INFO)
        s3transfer_logger.setLevel(logging.INFO)
    if pargs.verbose >= 3:
        botocore_logger.setLevel(logging.DEBUG)

    root_logger.addHandler(logging.StreamHandler(sys.stdout))

    try:
        pargs.func(parser, pargs)
    except Exception:
        log.exception("")
        sys.exit(1)
