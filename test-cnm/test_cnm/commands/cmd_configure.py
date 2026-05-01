import argparse
import logging
import sys

from test_cnm.config import ConfigBasic
from test_cnm.metadata import Metadata
from test_cnm.tester.collector import BucketTestCollector

log = logging.getLogger(__name__)


HELP = r"""
# Examples

To override the cnm queue config for all tests matching the 'ALOS' filter:

  tcnm configure ALOS \
    --cnm-ingest-queue alos1-workflow-queue \
    --cnm-response-queue alos1-mock-response-queue

To un-set the queue config override for all tests:

  tcnm configure "*" \
    --cnm-ingest-queue "" \
    --cnm-response-queue ""
"""

ATTRS = ("cnm_ingest_queue", "cnm_response_queue")


def add_parser(
    subparsers: argparse._SubParsersAction,
) -> argparse.ArgumentParser:
    parser_update_metadata = subparsers.add_parser(
        "configure",
        help="Update metadata file to set test level configuration",
        epilog=HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser_update_metadata.add_argument(
        "filter",
        help="Glob pattern to filter tests by. Can include '*', '?' and '[]' expressions",
        nargs="*",
        default=[],
    )
    properties_group = parser_update_metadata.add_argument_group("properties")
    properties_group.add_argument(
        "--cnm-ingest-queue",
        help="Override the cnm_ingest_queue that the CNM-S will be sent to for the tests",
    )
    properties_group.add_argument(
        "--cnm-response-queue",
        help="Override the cnm_response_queue that the CNM client will poll for the CNM-R response for the tests",
    )
    parser_update_metadata.set_defaults(
        func=cmd_update_metadata,
        config_cls=ConfigBasic,
    )

    return parser_update_metadata


def cmd_update_metadata(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
    config: ConfigBasic,
):
    filters = args.filter

    if not filters and any(getattr(args, attr) is not None for attr in ATTRS):
        log.error("No tests selected! If you would like to select all tests, please filter by '*'.")
        sys.exit(-1)

    session = config.session()

    collector = BucketTestCollector(
        session,
        config.test_bucket,
    )
    tests = collector.collect_tests(filters)

    with Metadata(session, config.test_bucket) as metadata:
        for test in tests.values():
            test_id = test.get_id()
            cfg = metadata.test_config[test_id]

            for attr in ATTRS:
                value = getattr(args, attr)
                if value:
                    log.debug("%s setting %s to %s", test_id, attr, value)
                    cfg[attr] = value
                elif value is not None and attr in cfg:
                    log.debug("%s unsetting %s", test_id, attr)
                    del cfg[attr]

            if cfg:
                log.info("%s:", test_id)
                for attr, value in cfg.items():
                    log.info("    %s: %s", attr, value)
