import logging
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Protocol, TypedDict

import boto3

log = logging.getLogger(__name__)


class FileDict(TypedDict):
    Bucket: str
    Key: str
    Size: int
    Md5Sum: str


@dataclass
class TestInfo:
    collection: str
    data_version: str
    name: str
    files: List[FileDict]
    cnm_s: Optional[dict] = None


class TestCollector(Protocol):
    def collect_tests(self, filters: List[str]) -> Dict[str, TestInfo]:
        ...


class BucketTestCollector:
    def __init__(self, session: boto3.Session, bucket: str, data_version: str):
        self.session = session
        self.test_bucket = bucket
        self.data_version = data_version

    def collect_tests(self, filters: List[str]) -> Dict[str, TestInfo]:
        client = self.session.client("s3")
        paginator = client.get_paginator("list_objects_v2")

        log.debug("Collecting tests from bucket %s", self.test_bucket)

        s3_entries = defaultdict(list)
        for response in paginator.paginate(Bucket=self.test_bucket):
            for entry in response.get("Contents", ()):
                key = entry["Key"]
                path = Path(key)
                if len(path.parts) < 3:
                    continue

                collection = path.parts[0]
                name = path.parts[-2]
                s3_entries[(collection, name)].append({
                    "Bucket": response["Name"],
                    "Key": key,
                    "Size": entry["Size"],
                    "ETag": entry["ETag"],
                    "Md5Sum": None,
                })

        return {
            name: TestInfo(
                collection,
                self.data_version,
                name,
                files,
            )
            for (collection, name), files in s3_entries.items()
            if not filters or any(
                f"{collection}/{name}".startswith(f)
                for f in filters
            )
        }
