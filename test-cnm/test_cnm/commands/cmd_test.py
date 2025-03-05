import argparse

from test_cnm.checksums import Checksums
from test_cnm.config import ConfigFull
from test_cnm.tester.cnm_generator import CnmSGenerator
from test_cnm.tester.collector import BucketTestCollector
from test_cnm.tester.executor import TestExecutor
from test_cnm.tester.ingest_client import CnmIngestClient


def add_parser(
    subparsers: argparse._SubParsersAction,
) -> argparse.ArgumentParser:
    parser_test = subparsers.add_parser(
        "test",
        help="Run a full end to end CNM ingest test",
    )
    parser_test.add_argument(
        "filter",
        help=(
            "Glob pattern to filter tests by. Can include '*', '?' and '[]' "
            "expressions"
        ),
        nargs="*",
        default=[],
    )
    parser_test.set_defaults(
        func=cmd_test,
        config_cls=ConfigFull,
    )

    return parser_test


def cmd_test(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
    config: ConfigFull,
):
    filters = args.filter

    session = config.session()

    checksums = Checksums(session, config.test_bucket)
    checksums.load()

    collector = BucketTestCollector(
        session,
        config.test_bucket,
    )
    ingest_client = CnmIngestClient(
        session=session,
        make_cnm_s=CnmSGenerator(
            provider=args.provider or "ASF-TESTCNM",
            trace=config.trace,
            checksums=checksums,
        ),
        start_queue=config.cnm_ingest_queue_name(),
        response_queue=config.cnm_response_queue_name(),
    )
    executor = TestExecutor(
        collector,
        ingest_client,
        config.default_data_version,
    )

    executor.run(filters)
