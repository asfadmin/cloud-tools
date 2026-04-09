import json
import logging
from collections.abc import Generator

from test_cnm.tester.cnm_generator import CnmSGenerator
from test_cnm.tester.ingest_client import CnmIngestClient
from test_cnm.tester.types import ExecutableTest, TestCollector

log = logging.getLogger(__name__)


class TestExecutor:
    def __init__(
        self,
        session,
        collector: TestCollector,
        make_cnm_s: CnmSGenerator,
        default_data_version: str,
        default_cnm_ingest_queue: str,
        default_cnm_response_queue: str,
    ):
        self.session = session
        self.collector = collector
        self.make_cnm_s = make_cnm_s
        self.default_data_version = default_data_version
        self.default_cnm_ingest_queue = default_cnm_ingest_queue
        self.default_cnm_response_queue = default_cnm_response_queue

    def new_test_run(self, filters: list[str]) -> "TestRun":
        return TestRun(self, filters)

    def run(self, filters: list[str]):
        self.new_test_run(filters).run()


class TestRun:
    def __init__(self, executor: TestExecutor, filters: list[str]):
        self.executor = executor
        self.filters = filters

        self.ingest_clients: dict[str, CnmIngestClient] = {}
        self.tests: list[ExecutableTest] = []
        self.pending_tests = {}
        # For deduplicating based on name. This is no longer strictly required
        # but may be desirable for now as it was the existing behavior. Cumulus
        # has also since pushed out an update to allow repeated granule ids
        # across multiple collections.
        self.pending_tests_by_name = {}

        # Stats
        self.num_skipped = 0
        self.num_started = 0
        self.num_succeeded = 0
        self.num_failed = 0

        self._state = "not_started"

    @property
    def num_completed(self) -> int:
        return self.num_succeeded + self.num_failed

    def _get_ingest_client(self, test: ExecutableTest) -> CnmIngestClient:
        key = test.cnm_response_queue

        if key not in self.ingest_clients:
            self.ingest_clients[key] = CnmIngestClient(
                session=self.executor.session,
                make_cnm_s=self.executor.make_cnm_s,
                cnm_response_queue=test.cnm_response_queue,
            )

        return self.ingest_clients[key]

    def _iter_ingest_client_responses(self) -> Generator[dict]:
        while True:
            clients_waiting = [
                # ruff hint
                client
                for client in self.ingest_clients.values()
                if client.is_waiting
            ]

            if not clients_waiting:
                return

            # Short poll first
            for ingest_client in clients_waiting[1:]:
                yield from ingest_client.process_messages()

            yield from clients_waiting[0].process_messages(wait_time_seconds=5)

    def run(self):
        self.collect_tests()
        for _ in self.iter_start_tests():
            pass
        for _ in self.iter_responses():
            pass
        self.log_summary()

    def collect_tests(self):
        assert self._state == "not_started", "Tests must be collected only once"

        # TODO: Resolve per-test ingest queue config somehow
        self.tests = [
            ExecutableTest(
                collection=test.collection,
                data_version=test.data_version,
                resolved_data_version=test.data_version or self.executor.default_data_version,
                name=test.name,
                files=test.files,
                cnm_ingest_queue=self.executor.default_cnm_ingest_queue,
                cnm_response_queue=self.executor.default_cnm_response_queue,
            )
            for test in self.executor.collector.collect_tests(self.filters).values()
        ]

        self._state = "tests_collected"

    def iter_start_tests(self) -> Generator[ExecutableTest]:
        assert self._state == "tests_collected", "Tests must be collected first"

        self.pending_tests.clear()
        self.pending_tests_by_name.clear()
        for test in self.tests:
            if test.name in self.pending_tests_by_name:
                log.warning(
                    "Skipping %s as the product name conflicts with already started test %s",
                    test.get_id(),
                    self.pending_tests_by_name[test.name].get_id(),
                )
                self.num_skipped += 1
                continue

            log.info("Starting: %s", test.get_id())
            test.cnm_s = self._get_ingest_client(test).submit_request(test)
            self.num_started += 1
            key = (test.cnm_s["identifier"], test.cnm_s["submissionTime"])
            self.pending_tests[key] = test
            self.pending_tests_by_name[test.name] = test

            yield test

        self._state = "tests_started"

    def iter_responses(self) -> Generator[tuple[ExecutableTest, dict]]:
        assert self._state == "tests_started", "Tests must be started first"

        for cnm_r in self._iter_ingest_client_responses():
            key = (cnm_r["identifier"], cnm_r["submissionTime"])
            test = self.pending_tests.pop(key)
            response = cnm_r.get("response", {})
            status = response.get("status")

            log.info("%s\t| %s", status, test.get_id())

            yield test, response

            if status == "SUCCESS":
                self.num_succeeded += 1
            else:
                self.num_failed += 1
                error_code = response.get("errorCode")
                error_message = response.get("errorMessage")
                try:
                    error = json.loads(error_message)
                    stack_trace = error.get("stackTrace") or error.get("trace", ())

                    log.error("%s: %s", error_code, error["errorMessage"])
                    log.error("".join(stack_trace))
                except (json.JSONDecodeError, TypeError):
                    log.error("%s: %s", error_code, error_message)

        self._state = "tests_completed"

    def log_summary(self):
        if self.pending_tests and self.num_completed != 0:
            for test in self.pending_tests.values():
                log.info("PENDING\t| %s", test.get_id())

        log.info(
            "Totals: %s Succeeded; %s Failed; %s Pending of %s tests%s",
            self.num_succeeded,
            self.num_failed,
            len(self.pending_tests),
            self.num_started,
            f" ({self.num_skipped} skipped)" if self.num_skipped else "",
        )
