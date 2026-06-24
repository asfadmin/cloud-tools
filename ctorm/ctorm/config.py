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
class CtormPipeline:
    bucketname: str

    # Looks for a keypair in the form of `AWS_ACCESS_KEY_ID_[keypair_name]`
    # This should have permissions to send SQS to the maturity we're sending CNM to
    ingest_keypair_name: str
    ingest_queue_name: str
    ingest_sqs_queue_url: str

    # Looks for a keypair in the form of `AWS_ACCESS_KEY_ID_[keypair_name]`
    # This should have permissions to read from prod bucket where data resides
    prepare_keypair_name: str
    share: int

    # These are used at runtime
    next_cont_token: str = None
    s3_client: S3Client = None
    session: Session = None
    ummg_prefix: str = "UMMG/"
    provider: str = "TODO"


@dataclass
class CtormConfig:
    pipelines: list
    granules_sqs_queue_url: str

    calc_md5: bool = True

    # This is the number of granules that will be prepared for test.
    granule_goal: int = 2000000

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
        # create CtormPipeline for each bucket in cfg['pipelines']
        kwargs["pipelines"] = [CtormPipeline(**b) for b in kwargs["pipelines"]]
        obj = cls(**kwargs)

        return obj
