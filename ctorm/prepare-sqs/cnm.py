import uuid
from datetime import datetime, timezone
from logging import getLogger
from typing import TypedDict

log = getLogger(__name__)


class CtormGranuleRow(TypedDict):
    c: str
    f: list[dict]
    n: str
    cv: str
    pk: str
    sk: str
    gsi1pk: str
    gsi1sk: str
    yyyymm: str
    collection: str
    granule_id: str
    load_test_count: int
    beginning_date_time: str


class CtormCnmSGenerator:
    PROVIDER: str = "ASF_LOAD_TESTER_PROVIDER"

    """input dict like:
        ```
    {
      "c": "OPERA_L2_CSLC-S1_V1",
      "f": [
        {
          "uri": "s3://bktname/path/to/file.png",
          "name": "file.png",
          "size": 59570,
          "type": "browse",
          "checksum": "f05e959d82aa7e35d6d22500f44acde4",
          "checksumType": "md5"
        },
        {
          "uri": "s3://bktname/path/to/file.png.md5",
          "name": "file.png.md5",
          "size": 32,
          "type": "metadata",
          "checksum": "4ff047c36b4ed6321e53017354f048b5",
          "checksumType": "md5"
        },
        {
          "uri": "s3://bktname2/OPERA_L2_CSLC-S1/file.xml",
          "name": "file",
          "size": 221607,
          "type": "metadata",
          "checksum": "c85d56fdc14a818863d81842184403db",
          "checksumType": "md5"
        },
        {
          "uri": "s3://bktname2/OPERA_L2_CSLC-S1/file.xml.md5",
          "name": "file.md5",
          "size": 32,
          "type": "metadata",
          "checksum": "8694488cc761bdce073eea44ea8ced8b",
          "checksumType": "md5"
        }
      ],
      "n": "OPERA_L2_CSLC-S1_T048-101257-IW2_20161015T233424Z_20240627T223207Z_S1B_VV_v1.1",
      "cv": "1",
      "pk": "OPERA_L2_CSLC-S1_V1#201610",
      "sk": "2016-10-15T23:34:24.000000Z#OPERA_L2_CSLC-S1_T048-101257-IW2_20161015T233424Z_20240627T223207Z_S1B_VV_v1.1",
      "gsi1pk": "OPERA_L2_CSLC-S1_T048-101257-IW2_20161015T233424Z_20240627T223207Z_S1B_VV_v1.1",
      "gsi1sk": "OPERA_L2_CSLC-S1_V1#201610",
      "yyyymm": "201610",
      "collection": "OPERA_L2_CSLC-S1_V1",
      "granule_id": "OPERA_L2_CSLC-S1_T048-101257-IW2_20161015T233424Z_20240627T223207Z_S1B_VV_v1.1",
      "load_test_count": 0,
      "beginning_date_time": "2016-10-15T23:34:24.000000Z"
    }
        ```
    """

    def __call__(self, granule_row: CtormGranuleRow) -> dict:
        # log.debug("Generating CNM for %s", granule_row.get("n", "?"))
        cnm_s = {
            "identifier": str(uuid.uuid4()),
            "collection": granule_row["c"],
            "version": "1.3",
            "submissionTime": datetime.now(tz=timezone.utc).strftime(
                "%Y-%m-%dT%H:%M:%S.%fZ"
            ),
            "product": {
                "name": granule_row["granule_id"],
                "dataVersion": granule_row["cv"],
                "files": granule_row["f"],
            },
            "provider": self.PROVIDER,
        }

        return cnm_s
