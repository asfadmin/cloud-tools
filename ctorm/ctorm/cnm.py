import re
import uuid
from collections.abc import Callable
from datetime import datetime, timezone
from logging import getLogger
from pathlib import Path

from ctorm.config import (
    MD5_CHECKSUM_PATTERN,
    CtormPipeline,
    CtormPreparedFile,
    CtormPreparedGranule,
)

log = getLogger(__name__)

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

type CtormCnmSGeneratorType = Callable[[CtormPreparedGranule, str], dict]  # noqa


class CtormCnmSGenerator:
    """input dict like:
    ```
    {
      "bm": {
        "sds-n-cumulus-prod-nisar-products": "B1",
        "sds-n-cumulus-prod-nisar-jpl-private-data": "B2"
      },
      "g": "NISAR_L0_RRST_VC08_20250821T101036_20250821T101041_P00408_J_001",
      "c": "NISAR_L0A_RRST_BETA_V1",
      "cv": "1",
      "f": [
        {
          "f": "s3://$B1/NISAR_L0A_RRST_BETA_V1/$G/$G.bin",
          "m": "e989430f4c5bfa04eeb26e56f4cd8375",
          "s": 1073829760
        },
        {
          "f": "s3://$B1/NISAR_L0A_RRST_BETA_V1/$G/$G.rc.yaml",
          "s": 120597,
          "m": "11bcaec780f0d246f3996b3f08680410"
        },
        {
          "f": "s3://$B1/NISAR_L0A_RRST_BETA_V1/$G/$G.bin.qa",
          "s": 1134,
        },
      ]
    },
    ```
    """

    def _assemble_file_dict(
        self, file_dict: CtormPreparedFile, g_name: str, bucket_map: dict
    ):
        file_s3uri = file_dict["f"].replace("$G", g_name)
        for bucket, replacetoken in bucket_map.items():
            file_s3uri = file_s3uri.replace(f"${replacetoken}", bucket)
        filename = Path(file_s3uri).name
        return {
            "name": filename,
            "type": self._get_type(filename),
            "uri": file_s3uri,
            "size": file_dict["s"],
            "checksum": self._get_checksum(file_dict),
            "checksumType": "md5",
        }

    def __call__(
        self,
        granule_dict: CtormPreparedGranule,
        provider: str,
    ) -> dict:
        cnm_s = {
            "identifier": str(uuid.uuid4()),
            "collection": granule_dict["c"],
            "version": "1.3",
            "submissionTime": datetime.now(tz=timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%S.%fZ"
            ),
            "product": {
                "name": granule_dict["g"],
                "dataVersion": granule_dict["cv"],
                "files": [
                    self._assemble_file_dict(
                        file, granule_dict["g"], granule_dict["bm"]
                    )
                    for file in granule_dict["f"]
                ],
            },
            "provider": provider,
        }

        return cnm_s

    def _get_type(self, filename: str):

        suffixes = Path(filename).suffixes
        while suffixes:
            data_type = DATA_TYPE_MAP.get("".join(suffixes))

            if data_type:
                return data_type

            suffixes = suffixes[1:]

        log.debug("suffix from %s is not in map. Using 'data'", filename)
        return "data"

    def _get_checksum(self, file_dict: CtormPreparedFile):
        m = MD5_CHECKSUM_PATTERN.match(file_dict.get("m", "not md5"))
        if m:
            return m.group(1)

        return "00000000000000000000000000000000"
