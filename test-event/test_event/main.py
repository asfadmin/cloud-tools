"""
A script for triggering ingest for event based ingest systems.

Run with --help for more information.
"""

import argparse
import logging
import sys
from typing import Optional

from test_event.commands import cmd_test

log = logging.getLogger(__name__)


def get_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    # parser.add_argument("ingest", help="Ingest system to trigger.")
    # parser.add_argument(
    #     "--environment",
    #     "-e",
    #     help="Config environment to use."
    # )
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
    root_logger.addHandler(logging.StreamHandler(sys.stdout))
    root_logger.setLevel(logging.INFO)


    try:
        pargs.func(parser, pargs)
    except Exception:
        log.exception("")
        sys.exit(1)
