import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from test_cnm.metadata import CHECKSUM_PATTERN, Metadata

DATA_TYPE_MAP = {
    ".context.json": "metadata",
    ".dataset.json": "metadata",
    ".h5": "data",
    ".iso.xml": "metadata",
    ".jpg": "browse",
    ".log": "metadata",
    ".md5": "metadata",
    ".met.json": "metadata",
    ".nc": "data",
    ".pdf": "qa",
    ".png": "browse",
    ".qa.h5": "qa",
    ".rc.yaml": "metadata",
    ".tif": "data",
    ".xml": "data",
}

CnmSGeneratorType = Callable[[str, str, str, list], dict]


class CnmSGenerator:
    def __init__(
        self,
        provider: str,
        trace: Optional[str] = None,
        metadata: Optional[Metadata] = None,
    ):
        self.provider = provider
        self.trace = trace
        self.metadata = metadata

    def __call__(
        self,
        collection: str,
        data_version: str,
        name: str,
        files: list,
    ) -> dict:
        cnm_s = {
            "identifier": str(uuid.uuid4()),
            "collection": collection,
            "version": "1.3",
            "submissionTime": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "product": {
                "name": name,
                "dataVersion": data_version,
                "files": [
                    {
                        "name": Path(file["Key"]).name,
                        "type": self._get_type(file),
                        "uri": f"s3://{file['Bucket']}/{file['Key']}",
                        "size": file["Size"],
                        "checksum": self._get_checksum(file),
                        "checksumType": "md5",
                    }
                    for file in files
                ],
            },
            "provider": self.provider,
        }
        if self.trace:
            cnm_s["trace"] = self.trace

        return cnm_s

    def _get_type(self, file: dict):
        key = file["Key"]
        if self.metadata and key in self.metadata:
            metadata_entry = self.metadata[key]
            if "type" in metadata_entry:
                return metadata_entry["type"]

        suffixes = Path(key).suffixes
        while suffixes:
            data_type = DATA_TYPE_MAP.get("".join(suffixes))
            if data_type:
                return data_type

            suffixes = suffixes[1:]

        return "data"

    def _get_checksum(self, file: dict):
        key = file["Key"]
        if self.metadata and key in self.metadata:
            return self.metadata[key]["checksum"]

        m = CHECKSUM_PATTERN.match(file["ETag"])
        if m:
            return m.group(1)

        return "00000000000000000000000000000000"
