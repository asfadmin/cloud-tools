import argparse
import configparser
from dataclasses import MISSING, dataclass, fields
from typing import Optional, Union

import boto3

DEFAULT = "default"


class ConfigError(Exception):
    pass


@dataclass
class ConfigBase:
    @classmethod
    def from_file(
        cls,
        filenames: Union[str, list[str]],
        args: Optional[argparse.Namespace] = None,
    ) -> "ConfigBase":
        config = configparser.ConfigParser(default_section=None)
        config.read(filenames)

        options = {} if args is None else vars(args)
        env = options.get("environment") or DEFAULT

        if args is None and not config.has_section(env):
            raise ConfigError(f"environment '{env}' not found")

        section = config[env] if config.has_section(env) else {}
        default_section = config[DEFAULT] if config.has_section(DEFAULT) else {}

        def _get_value(key: str, default=None):
            if (val := options.get(key)) is not None:
                return val
            if (val := section.get(key)) is not None:
                return val
            if (val := default_section.get(key)) is not None:
                return val

            return default

        kwargs = {
            # ruff hint
            field.name: _get_value(field.name, default=field.default)
            for field in fields(cls)
        }
        missing = [
            # ruff hint
            k
            for field, (k, v) in zip(fields(cls), kwargs.items())
            if v is MISSING
        ]
        if missing:
            raise ConfigError(f"missing values for {missing} for environment '{env}'")

        return cls(**kwargs)


@dataclass
class ConfigBasic(ConfigBase):
    test_bucket: str
    profile: Optional[str] = None

    def session(self) -> boto3.Session:
        return boto3.Session(profile_name=self.profile)


@dataclass
class ConfigFull(ConfigBase):
    # TODO(reweeden): In python3.10 dataclasses support keyword only arguments
    # which would let us refactor this duplication
    test_bucket: str
    cnm_ingest_queue: str
    cnm_response_queue: str
    provider: str
    default_data_version: str = "1.0"
    stack_name: Optional[str] = None
    trace: Optional[str] = None
    # TODO(reweeden): python3.10 refactor duplication
    profile: Optional[str] = None

    def session(self) -> boto3.Session:
        return boto3.Session(profile_name=self.profile)

    def cnm_ingest_queue_name(self) -> str:
        if self.stack_name and not self.cnm_ingest_queue.startswith(self.stack_name):
            return f"{self.stack_name}-{self.cnm_ingest_queue}"

        return self.cnm_ingest_queue

    def cnm_response_queue_name(self) -> str:
        if self.stack_name and not self.cnm_response_queue.startswith(self.stack_name):
            return f"{self.stack_name}-{self.cnm_response_queue}"

        return self.cnm_response_queue
