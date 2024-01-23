import argparse

from test_cnm.checksums import Checksums
from test_cnm.config import Config
from test_cnm.tester.cnm_generator import CnmSGenerator
from test_cnm.tester.collector import BucketTestCollector
from test_cnm.tester.executor import TestExecutor
from test_cnm.tester.ingest_client import CnmIngestClient


def add_parser(
    subparsers: argparse._SubParsersAction,
) -> argparse.ArgumentParser:
    parser_load_test = subparsers.add_parser(
        "load-test",
        help="Run a load test on the CNM ingest system",
    )
    parser_load_test.add_argument(
        "--number-of-ingests",  # TODO: (McKade) Update this to be more clear
        help="Number of times to run 1 of each collection",
        type=int,
        default=5,
    )
    parser_load_test.add_argument(
        "filter",
        help="Run tests matching this prefix. Multiple filters are or'd together",
        nargs="*",
        default=[],
    )
    parser_load_test.set_defaults(func=cmd_load_test)

    return parser_load_test


def cmd_load_test(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
    config: Config
):
    for i in range(args.number_of_ingests):
        # TODO: (McKade) Clean up this print statement
        print(f"Running ingest {i + 1} of {args.number_of_ingests}")

        # TODO: (McKade) Update how this is done
        filters = args.filter

        session = config.session()

        checksums = Checksums(session, config.test_bucket)
        checksums.load()

        collector = BucketTestCollector(
            session,
            config.test_bucket,
            config.data_version,
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
        executor = TestExecutor(collector, ingest_client)

        executor.run(filters)

