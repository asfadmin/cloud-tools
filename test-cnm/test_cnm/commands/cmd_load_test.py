import argparse
import logging
import time

from test_cnm.checksums import Checksums
from test_cnm.config import Config
from test_cnm.tester.cnm_generator import CnmSGenerator
from test_cnm.tester.collector import BucketTestCollector
from test_cnm.tester.executor import LoadTestExecutor
from test_cnm.tester.ingest_client import CnmIngestClient

log = logging.getLogger(__name__)


def add_parser(
    subparsers: argparse._SubParsersAction,
) -> argparse.ArgumentParser:
    parser_load_test = subparsers.add_parser(
        "load-test",
        help="Run a load test on the CNM ingest system",
    )
    parser_load_test.add_argument(
        "--number-of-ingests",
        help="Number of times to run 1 of each product in a bucket",
        type=int,
        default=5,
    )
    parser_load_test.add_argument(
        "filter",
        help="Run tests matching this prefix. Multiple filters are or'd together",
        nargs="*",
        default=[],
    )
    parser_load_test.add_argument(
        "--duration",
        help="Duration of the load test in seconds",
        default=60*5,
        type=int,
    )
    parser_load_test.set_defaults(func=cmd_load_test)

    return parser_load_test


def run_ingest(
        args: argparse.Namespace,
        config: Config
):
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
    executor = LoadTestExecutor(collector, ingest_client)

    executor.run(filters)


def cmd_load_test(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
    config: Config
):
    ingest_rate = args.duration / args.number_of_ingests

    for ingest in range(args.number_of_ingests):
        log.info("Running ingest %d of %d", ingest + 1, args.number_of_ingests)
        run_ingest(args, config)

        if ingest != args.number_of_ingests - 1:
            log.info("Next ingest in %d seconds", ingest_rate)
            time.sleep(ingest_rate)
