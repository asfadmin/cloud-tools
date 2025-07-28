import json
import logging
from collections.abc import Generator

from test_cnm.tester.collector import TestCollector, TestInfo
from test_cnm.tester.ingest_client import CnmIngestClient

log = logging.getLogger(__name__)


class TestExecutor:
    def __init__(
        self,
        collector: TestCollector,
        ingest_client: CnmIngestClient,
        default_data_version: str,
    ):
        self.collector = collector
        self.ingest_client = ingest_client
        self.default_data_version = default_data_version

    def new_test_run(self, filters: list[str]) -> "TestRun":
        return TestRun(self, filters)

    def run(self, filters: list[str]):
        self.new_test_run(filters).run()


class TestRun:
    def __init__(self, executor: TestExecutor, filters: list[str]):
        self.executor = executor
        self.filters = filters

        self.tests = {}
        self.pending_tests = {}

        # Stats
        self.num_started = 0
        self.num_succeeded = 0
        self.num_failed = 0

        self._state = "not_started"

    @property
    def num_completed(self) -> int:
        return self.num_succeeded + self.num_failed

    def run(self):
        self.collect_tests()
        for _ in self.iter_start_tests():
            pass
        for _ in self.iter_responses():
            pass
        self.log_summary()

    def collect_tests(self):
        assert self._state == "not_started", "Tests must be collected only once"

        # Collect
        self.tests = self.executor.collector.collect_tests(self.filters)

        self._state = "tests_collected"

    def iter_start_tests(self) -> Generator[TestInfo]:
        assert self._state == "tests_collected", "Tests must be collected first"

        self.pending_tests.clear()
        for test in self.tests.values():
            if test.name in self.pending_tests:
                log.warning(
                    "Skipping %s as the product name conflicts with already "
                    "started test %s",
                    test.get_id(),
                    self.pending_tests[test.name].get_id(),
                )
                continue

            log.info("Starting: %s", test.get_id())
            test.cnm_s = self.executor.ingest_client.submit_request(
                test.collection,
                test.data_version or self.executor.default_data_version,
                test.name,
                test.files,
            )
            self.num_started += 1
            self.pending_tests[test.name] = test

            yield test

        self._state = "tests_started"

    def iter_responses(self) -> Generator[tuple[TestInfo, dict]]:
        assert self._state == "tests_started", "Tests must be started first"

        for name, cnm_r in self.executor.ingest_client.iter_responses():
            test = self.pending_tests.pop(name)
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
            "Totals: %s Succeeded; %s Failed of %s tests",
            self.num_succeeded,
            self.num_failed,
            self.num_started,
        )
