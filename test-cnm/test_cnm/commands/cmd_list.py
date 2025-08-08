import argparse
import logging
from collections import defaultdict
from pathlib import Path

from common.config import ConfigBasic
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
        "--files",
        help="Display file list along with each test",
        action="store_true",
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
    parser_list.set_defaults(
        func=cmd_list,
        config_cls=ConfigBasic,
    )

    return parser_list


def cmd_list(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
    config: ConfigBasic,
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
            test_id = test.get_id().removeprefix(prefix)
            log.info("  - %s (%d files)", test_id, len(test.files))
            if args.files:
                last_idx = len(test.files) - 1
                for i, file in enumerate(test.files):
                    bar = "└" if i == last_idx else "├"
                    log.info("    %s── %s", bar, Path(file["Key"]).name)

    log.info("\nTotals: %s Collections; %s Tests", len(tests_by_collection), len(tests))
