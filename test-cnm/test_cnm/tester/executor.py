import json
import logging
from typing import List

from test_cnm.tester.collector import TestCollector
from test_cnm.tester.ingest_client import CnmIngestClient

log = logging.getLogger(__name__)


class TestExecutor:
    def __init__(
        self,
        collector: TestCollector,
        ingest_client: CnmIngestClient,
    ):
        self.collector = collector
        self.ingest_client = ingest_client

    def run(self, filters: List[str]):
        # Collect
        tests = self.collector.collect_tests(filters)

        # Start
        for test in tests.values():
            log.info("Starting: %s/%s", test.collection, test.name)
            test.cnm_s = self.ingest_client.submit_request(
                test.collection,
                test.data_version,
                test.name,
                test.files,
            )

        # Response
        num_failed = 0
        for name, cnm_r in self.ingest_client.iter_responses():
            test = tests[name]
            response = cnm_r.get("response", {})
            status = response.get("status")
            ok = _response_ok(cnm_r)

            log.info("%s\t%s\t| %s/%s", ok, status, test.collection, test.name)

            if not ok:
                num_failed += 1
                error_code = response["errorCode"]
                error_message = response["errorMessage"]
                try:
                    error = json.loads(error_message)
                    stack_trace = error.get("stackTrace") or error.get("trace", ())

                    log.error("%s: %s", error_code, error["errorMessage"])
                    log.error("".join(stack_trace))
                except json.JSONDecodeError:
                    log.error("%s: %s", error_code, error_message)

        num_total = len(tests)
        num_success = num_total - num_failed
        log.info(
            "Totals: %s Succeeded; %s Failed of %s tests",
            num_success,
            num_failed,
            num_total,
        )


class LoadTestExtractor(TestExecutor):
    def run(self, filters: List[str]):
        tests = self.collector.collect_tests(filters)

        # TODO: (McKade) Refactor
        for test in tests.values():
            log.info("Starting: %s/%s", test.collection, test.name)
            test.cnm_s = self.ingest_client.submit_request(
                test.collection,
                test.data_version,
                test.name,
                test.files,
            )


def _response_ok(cnm_r: dict) -> bool:
    return cnm_r.get("response", {}).get("status") == "SUCCESS"
