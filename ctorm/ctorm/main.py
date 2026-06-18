"""
A script for load testing cumulus.

"""

import argparse
import logging
import sys
from typing import Optional

from ctorm.commands import cmd_cnm_sender, cmd_prepare

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

    parser.add_argument("--profile", help="AWS profile name")
    parser.add_argument(
        "--cfg-file",
        help="Config file",
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    prepare_parser = subparsers.add_parser(
        "prepare",
        help="Fill the granules SQS queue with work for the load test.",
    )
    prepare_parser.add_argument(
        "--source-bucket",
        help="S3 bucket source granules",
    )
    prepare_parser.set_defaults(func=cmd_prepare)

    cnm_sender_parser = subparsers.add_parser(
        "cnm_sender",
        help="Read queued work and formulate load-test/CNM messages.",
    )
    cnm_sender_parser.add_argument(
        "--max-messages",
        type=int,
        default=-1,  # -1 is unlimited
        help="Maximum number of SQS messages to process in one invocation. Default is unlimited.",
    )
    cnm_sender_parser.set_defaults(func=cmd_cnm_sender)

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

    if pargs.verbose >= 1:
        root_logger.setLevel(logging.DEBUG)
    if pargs.verbose >= 2:
        boto3_logger.setLevel(logging.DEBUG)
        botocore_logger.setLevel(logging.INFO)
        urllib3_logger.setLevel(logging.DEBUG)
        s3transfer_logger.setLevel(logging.DEBUG)
    if pargs.verbose >= 3:
        botocore_logger.setLevel(logging.DEBUG)

    base_fmt_str = "%(levelname)s: %(message)s (%(filename)s line %(lineno)d/)"
    screen_fmt = logging.Formatter("%(asctime)s.%(msecs)d " + base_fmt_str, "%Y-%m-%dT%H:%M:%S")
    screenlog = logging.StreamHandler()
    screenlog.setFormatter(screen_fmt)
    root_logger.addHandler(screenlog)

    try:
        pargs.func(pargs)

    except Exception:
        log.exception("")
        sys.exit(-1)
