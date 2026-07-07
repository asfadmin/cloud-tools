import re
import tomllib
from dataclasses import dataclass, fields
from typing import NotRequired, TypedDict

from boto3.session import Session
from mypy_boto3_s3 import S3Client

try:
    from typing import Self
except ImportError:
    Self = "CtormConfig"

DEFAULT = "default"
AWS_REGION = "us-west-2"  # We will never not want us-west-2
MD5_CHECKSUM_PATTERN = re.compile(r"^([\da-f]{32})$")


class CtormPreparedFile(TypedDict):
    f: str
    m: NotRequired[str]
    s: int


class CtormPreparedGranule(TypedDict):
    bm: dict[str, str]
    g: str
    c: str
    cv: str
    f: list[CtormPreparedFile]


@dataclass
class PrepSqsMsgCollection:
    collection: str
    num_of_granules: int
    start_date: int
    end_date: int


@dataclass
class PrepSqsConfig:
    maturity: str
    dyndb_tablename: str

    granule_goal: int
    msg_collections: list[PrepSqsMsgCollection]

    @classmethod
    def from_file(
            cls,
            cfg_file: str,
    ) -> Self:
        with open(cfg_file, "rb") as f:
            cfg = tomllib.load(f)
        valid_fields = {f.name for f in fields(cls)}
        # Filter the input dictionary
        kwargs = {k: v for k, v in cfg["ctorm"].items() if k in valid_fields}
        # create PrepSqsMsgCollection for each bucket in cfg['msg_collections']
        kwargs["msg_collections"] = [
            PrepSqsMsgCollection(**b) for b in kwargs["msg_collections"]
        ]
        obj = cls(**kwargs)

        return obj
