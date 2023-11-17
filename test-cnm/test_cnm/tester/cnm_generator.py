from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional

from test_cnm.checksums import CHECKSUM_PATTERN, Checksums

DATA_TYPE_MAP = {
    ".context.json": "metadata",
    ".dataset.json": "metadata",
    ".h5": "data",
    ".iso.xml": "metadata",
    ".md5": "metadata",
    ".met.json": "metadata",
    ".xml": "data",
}

CnmSGeneratorType = Callable[[str, str, list], dict]


class CnmSGenerator:
    def __init__(
        self,
        provider: str,
        trace: Optional[str] = None,
        checksums: Optional[Checksums] = None,
    ):
        self.provider = provider
        self.trace = trace
        self.checksums = checksums

    def __call__(
        self,
        collection: str,
        name: str,
        files: list,
    ) -> dict:
        cnm_s = {
            "identifier": name,
            "collection": collection,
            "version": "1.3",
            "submissionTime": datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ"),
            "product": {
                "name": name,
                "dataVersion": "1.0",
                "files": [
                    {
                        "name": Path(file["Key"]).name,
                        "type": self._get_type(file),
                        "uri": f"s3://{file['Bucket']}/{file['Key']}",
                        "size": file["Size"],
                        "checksum": self._get_checksum(file),
                        "checksumType": "md5"
                    }
                    for file in files
                ]
            },
            "provider": self.provider,
        }
        if self.trace:
            cnm_s["trace"] = self.trace

        return cnm_s

    def _get_type(self, file: dict):
        suffixes = Path(file["Key"]).suffixes
        while suffixes:
            data_type = DATA_TYPE_MAP.get("".join(suffixes))
            if data_type:
                return data_type

            suffixes = suffixes[1:]

        return "data"

    def _get_checksum(self, file: dict):
        key = file["Key"]
        if self.checksums and key in self.checksums:
            return self.checksums[key]

        m = CHECKSUM_PATTERN.match(file["ETag"])
        if m:
            return m.group(1)

        return "00000000000000000000000000000000"
