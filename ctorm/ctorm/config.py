import tomllib
from dataclasses import dataclass, fields

try:
    from typing import Self
except ImportError:
    Self = "CtormConfig"

DEFAULT = "default"
AWS_REGION = "us-west-2"  # We will never not want us-west-2


@dataclass
class CtormBucket:
    bucketname: str
    share: int = ""

    next_cont_token: str = None
    ummg_prefix: str = "UMMG/"


@dataclass
class CtormConfig:
    source_buckets: list
    granules_sqs_queue_url: str

    @classmethod
    def from_file(
        cls,
        cfg_file: str,
    ) -> Self:
        with open(cfg_file, "rb") as f:
            cfg = tomllib.load(f)
        if "ctorm" in cfg:
            cfg = cfg["ctorm"]
        else:
            raise KeyError("No 'ctorm' section in config file")
        valid_fields = {f.name for f in fields(cls)}
        # Filter the input dictionary
        kwargs = {k: v for k, v in cfg.items() if k in valid_fields}
        # create CtormBuckets for each bucket in cfg['source_buckets']
        kwargs["source_buckets"] = [CtormBucket(**b) for b in kwargs["source_buckets"]]
        obj = cls(**kwargs)

        return obj
