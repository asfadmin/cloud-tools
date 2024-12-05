import json
import logging

from test_cnm.tester.collector import TestCollector
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

    def run(self, filters: list[str]):
        # Collect
        tests = self.collector.collect_tests(filters)

        # Start
        for test in tests.values():
            log.info("Starting: %s", test.get_id())
            test.cnm_s = self.ingest_client.submit_request(
                test.collection,
                test.data_version or self.default_data_version,
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

            log.info("%s\t%s\t| %s", ok, status, test.get_id())

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


def _response_ok(cnm_r: dict) -> bool:
    return cnm_r.get("response", {}).get("status") == "SUCCESS"
