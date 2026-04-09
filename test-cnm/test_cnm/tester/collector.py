import fnmatch
import logging
import re
from collections import defaultdict
from pathlib import Path
from typing import Optional

import boto3
from test_cnm.tester.types import FileDict, TestInfo

log = logging.getLogger(__name__)

DATA_VERSION_PATTERN = re.compile(r"^\d+\.\d+|\d$")


class BucketTestCollector:
    def __init__(self, session: boto3.Session, bucket: str):
        self.session = session
        self.test_bucket = bucket

    def collect_tests(self, filters: list[str]) -> dict[str, TestInfo]:
        client = self.session.client("s3")
        paginator = client.get_paginator("list_objects_v2")

        log.debug("Collecting tests from bucket %s", self.test_bucket)

        s3_entries: dict[tuple[str, Optional[str], str], list[FileDict]] = defaultdict(list)
        for response in paginator.paginate(Bucket=self.test_bucket):
            for entry in response.get("Contents", ()):
                key = entry["Key"]
                path = Path(key)
                if len(path.parts) < 3:
                    continue

                collection = path.parts[0]
                data_version = path.parts[1] if DATA_VERSION_PATTERN.fullmatch(path.parts[1]) else None
                name = path.parts[-2]
                s3_entries[collection, data_version, name].append(
                    {
                        "Bucket": response["Name"],
                        "Key": key,
                        "Size": entry["Size"],
                        "ETag": entry["ETag"],
                    }
                )

        return {
            test.get_id(): test
            for (collection, data_version, name), files in s3_entries.items()
            if _match_filters(
                filters,
                (
                    test := TestInfo(
                        collection,
                        data_version,
                        name,
                        sorted(files, key=lambda file: Path(file["Key"]).name),
                    )
                ),
            )
        }


def _match_filters(filters: list[str], test: TestInfo) -> bool:
    if not filters:
        return True

    test_id = test.get_id()

    return any(fnmatch.fnmatchcase(test_id, f + "*") for f in filters)
