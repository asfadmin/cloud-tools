import argparse
import logging
from collections import defaultdict

from test_cnm.config import Config
from test_cnm.tester.collector import BucketTestCollector

log = logging.getLogger(__name__)


def add_parser(
    subparsers: argparse._SubParsersAction,
) -> argparse.ArgumentParser:
    parser_list = subparsers.add_parser(
        "list",
        aliases=["ls"],
        help="List available test products",
    )
    parser_list.add_argument(
        "filter",
        help=(
            "Glob pattern to filter tests by. Can include '*', '?' and '[]' "
            "expressions"
        ),
        nargs="*",
        default=[],
    )
    parser_list.set_defaults(func=cmd_list)

    return parser_list


def cmd_list(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
    config: Config,
):
    filters = args.filter

    session = config.session()

    collector = BucketTestCollector(
        session,
        config.test_bucket,
    )
    tests = collector.collect_tests(filters)

    tests_by_collection = defaultdict(list)
    for test in tests.values():
        tests_by_collection[test.collection].append(test)

    # Start
    for collection, grouped_tests in tests_by_collection.items():
        log.info("%s:", collection)
        for test in grouped_tests:
            prefix = f"{collection}/"
            test_id = test.get_id()
            # TODO(reweeden): Python3.9+ use 'removeprefix'
            if test_id.startswith(prefix):
                test_id = test_id[len(prefix):]
            log.info("  - %s", test_id)

    log.info("\nTotals: %s Collections; %s Tests", len(tests_by_collection), len(tests))
