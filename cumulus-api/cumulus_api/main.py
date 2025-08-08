import argparse
import json
import logging
import sys
from importlib.metadata import Distribution
from platform import python_version
from typing import Optional

from cumulus_api.commands import cmd_curl, cmd_deploy

try:
    from cumulus_api.commands import cmd_report
except ImportError:
    cmd_report = None

log = logging.getLogger(__name__)


def _get_version() -> str:
    name = "cumulus-api"
    dist = Distribution.from_name(name)
    direct_url = json.loads(dist.read_text("direct_url.json"))
    editable = direct_url.get("dir_info", {}).get("editable", False)
    return (
        f"{name} {'(editable) ' if editable else ''}{dist.version} "
        f"on Python {python_version()}"
    )


def get_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()

    parser.add_argument("--version", action="version", version=_get_version())

    subparsers = parser.add_subparsers(
        metavar="subcommand",
        required=True,
        # Without this, the 'required' option doesn't work
        dest="command",
    )

    add_subcommand(subparsers, cmd_curl)
    add_subcommand(subparsers, cmd_deploy)
    if cmd_report:
        add_subcommand(subparsers, cmd_report)

    return parser


def add_subcommand(subparsers: argparse._SubParsersAction, cmd_module):
    parser = cmd_module.add_parser(subparsers)
    common_group = parser.add_argument_group("common")
    add_common_args(common_group)


def add_common_args(parser: argparse._ActionsContainer):
    parser.add_argument(
        "-v",
        "--verbose",
        help="print debug information",
        action="store_true",
    )
    parser.add_argument("--profile", help="AWS profile to use")
    parser.add_argument("--deploy-name", help="deployment name", default="asf")
    parser.add_argument("--maturity", help="deployment maturity", default="dev")
    parser.add_argument(
        "--lambda",
        help="name of lambda that handles API requests",
        default="PrivateApiLambda",
        dest="lambda_name",
    )
    parser.add_argument(
        "--api-version",
        help="Cumulus API Version to use",
        type=int,
        default=1,
        dest="cumulus_api_version",
    )


def main(args: Optional[list[str]] = None):
    parser = get_parser()
    pargs = parser.parse_args(args=args)

    # Set up console logger
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

    if pargs.verbose:
        root_logger.setLevel(logging.DEBUG)

    root_logger.addHandler(logging.StreamHandler(sys.stdout))

    log.debug("calling %s", pargs.func)
    pargs.func(pargs)
