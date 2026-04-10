"""
A script for simulating a CNM invocation using sample products stored in a
testing bucket. Any errors returned in the CNM-R will be printed to the
console along with a summary of the number of errors encountered.

Run with --help for more information.
"""

import argparse
import json
import logging
import os
import sys
from importlib.metadata import Distribution, PackageNotFoundError
from platform import python_version
from typing import Optional

from test_cnm.commands import (
    cmd_configure,
    cmd_list,
    cmd_move,
    cmd_test,
    cmd_tidy,
    cmd_update_metadata,
    cmd_upload,
)

log = logging.getLogger(__name__)

LOG_HANDLER = logging.StreamHandler(sys.stdout)


def _get_version() -> str:
    name = "test-cnm"
    try:
        dist = Distribution.from_name(name)
        direct_url = json.loads(dist.read_text("direct_url.json"))
        editable = direct_url.get("dir_info", {}).get("editable", False)
        return f"{name} {'(editable) ' if editable else ''}{dist.version} on Python {python_version()}"
    except PackageNotFoundError:
        return f"{name} from source on Python {python_version()}"


def get_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()

    parser.add_argument("--version", action="version", version=_get_version())
    parser.add_argument(
        "--verbose",
        "-v",
        help="Increase verbosity level. Can be passed multiple times.",
        action="count",
        default=0,
    )
    parser.add_argument(
        "--environment",
        "-e",
        help="Config environment to use. Config is read from a testcnm.cfg file in the current directory.",
    )
    parser.add_argument("--profile", help="AWS profile name")
    parser.add_argument(
        "--test-bucket",
        help="S3 bucket containing E2E test data",
    )
    # TODO(reweeden): So far the rest of these are only used in the 'test'
    # command. Maybe make them optional in config and move to 'test' parser.
    parser.add_argument(
        "--stack-name",
        help="Cumulus prefix e.g. sds-n-cumulus-dev",
    )
    parser.add_argument(
        "--cnm-ingest-queue",
        help="Queue name where CNM-S messages will be sent",
    )
    parser.add_argument(
        "--cnm-response-queue",
        help="Queue name to poll for CNM-R responses",
    )
    parser.add_argument(
        "--provider",
        help="Name of the CNM-S provider",
    )
    parser.add_argument(
        "--default-data-version",
        help="Data version to use in the CNM-S if none is explicitly set in the object key",
    )
    parser.add_argument(
        "--trace",
        help="Value for the CNM-S trace element",
    )

    subparsers = parser.add_subparsers(
        title="command",
        required=True,
        # Without this, the 'required' option doesn't work
        dest="command",
    )

    cmd_configure.add_parser(subparsers)
    cmd_list.add_parser(subparsers)
    cmd_move.add_parser(subparsers)
    cmd_test.add_parser(subparsers)
    cmd_tidy.add_parser(subparsers)
    cmd_update_metadata.add_parser(subparsers)
    cmd_upload.add_parser(subparsers)

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

    if LOG_HANDLER not in root_logger.handlers:
        root_logger.addHandler(LOG_HANDLER)

    config_cls = pargs.config_cls
    config = config_cls.from_file(
        ["testcnm.cfg", os.path.expanduser("~/testcnm.cfg")],
        args=pargs,
    )
    try:
        log.debug("Using config: %s", config)
        pargs.func(parser, pargs, config)
    except Exception:
        log.exception("")
        sys.exit(-1)
