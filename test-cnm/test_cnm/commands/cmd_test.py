import argparse
import logging

from test_cnm.config import ConfigFull
from test_cnm.metadata import Metadata
from test_cnm.tester.cnm_generator import CnmSGenerator
from test_cnm.tester.collector import BucketTestCollector
from test_cnm.tester.executor import TestExecutor
from test_cnm.tester.ingest_client import CnmIngestClient
from tqdm import tqdm
from tqdm.contrib.logging import logging_redirect_tqdm

log = logging.getLogger(__name__)


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
            "Glob pattern to filter tests by. Can include '*', '?' and '[]' expressions"
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

    metadata = Metadata(session, config.test_bucket)
    metadata.load()

    collector = BucketTestCollector(
        session,
        config.test_bucket,
    )
    ingest_client = CnmIngestClient(
        session=session,
        make_cnm_s=CnmSGenerator(
            provider=args.provider or "ASF-TESTCNM",
            trace=config.trace,
            metadata=metadata,
        ),
        start_queue=config.cnm_ingest_queue_name(),
        response_queue=config.cnm_response_queue_name(),
    )
    executor = TestExecutor(
        collector,
        ingest_client,
        config.default_data_version,
    )

    log.info("Executing tests on %s", config.stack_name)

    test_run = executor.new_test_run(filters)
    try:
        test_run.collect_tests()

        with logging_redirect_tqdm():
            with tqdm(
                total=len(test_run.tests),
                miniters=1,
                leave=False,
                desc=config.stack_name,
                bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} started ",
            ) as t:
                for _ in test_run.iter_start_tests():
                    t.update()

            with tqdm(
                total=test_run.num_started,
                miniters=1,
                leave=False,
                desc=config.stack_name,
                bar_format="{l_bar}{bar}| {n_fmt}/{total_fmt} finished ",
            ) as t:
                for _ in test_run.iter_responses():
                    t.update()
    except KeyboardInterrupt:
        test_run.log_summary()
    else:
        test_run.log_summary()
