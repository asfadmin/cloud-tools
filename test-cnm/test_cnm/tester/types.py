from dataclasses import dataclass
from typing import Optional, Protocol, TypedDict


class FileDict(TypedDict):
    Bucket: str
    Key: str
    Size: int
    ETag: str


@dataclass
class TestInfo:
    collection: str
    data_version: Optional[str]
    name: str
    files: list[FileDict]

    def get_id(self) -> str:
        if self.data_version:
            return f"{self.collection}/{self.data_version}/{self.name}"

        return f"{self.collection}/{self.name}"


@dataclass
class ExecutableTest(TestInfo):
    resolved_data_version: str
    cnm_ingest_queue: str
    cnm_response_queue: str
    provider: str
    trace: Optional[str] = None
    cnm_s: Optional[dict] = None


class TestCollector(Protocol):
    def collect_tests(self, filters: list[str]) -> dict[str, TestInfo]: ...
