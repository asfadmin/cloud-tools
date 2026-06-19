import tomllib
from dataclasses import dataclass, fields

from boto3.session import Session
from mypy_boto3_s3 import S3Client

try:
    from typing import Self
except ImportError:
    Self = "CtormConfig"

DEFAULT = "default"
AWS_REGION = "us-west-2"  # We will never not want us-west-2


@dataclass
class CtormBucket:
    bucketname: str
    keypair_name: str  # Looks for a keypair in the form of `AWS_ACCESS_KEY_ID_[keypair_name]`
    share: int = ""

    next_cont_token: str = None
    s3_client: S3Client = None
    session: Session = None
    ummg_prefix: str = "UMMG/"


@dataclass
class CtormConfig:
    source_buckets: list
    granules_sqs_queue_url: str

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
        # create CtormBuckets for each bucket in cfg['source_buckets']
        kwargs["source_buckets"] = [CtormBucket(**b) for b in kwargs["source_buckets"]]
        obj = cls(**kwargs)

        return obj
