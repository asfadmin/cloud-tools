import argparse
import configparser
from collections.abc import Mapping
from dataclasses import MISSING, dataclass, field, fields, replace
from typing import Optional, Union

try:
    from typing import Self
except ImportError:
    Self = "ConfigBase"

import boto3

DEFAULT = "default"


class ConfigError(Exception):
    pass


@dataclass
class ConfigBase:
    _options: Optional[dict[str, str]] = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )
    _section: Optional[dict[str, str]] = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )
    _default_section: Optional[dict[str, str]] = field(
        default=None,
        init=False,
        repr=False,
        compare=False,
    )

    @classmethod
    def from_file(
        cls,
        filenames: Union[str, list[str]],
        args: Optional[argparse.Namespace] = None,
    ) -> Self:
        config = configparser.ConfigParser(default_section=None)
        config.read(filenames)

        options = {} if args is None else vars(args)
        env = options.get("environment") or DEFAULT

        if args is None and not config.has_section(env):
            raise ConfigError(f"environment '{env}' not found")

        section = config[env] if config.has_section(env) else {}
        default_section = config[DEFAULT] if config.has_section(DEFAULT) else {}

        kwargs = cls._resolve_kwargs(
            options=options,
            section=section,
            default_section=default_section,
        )
        missing = [
            # ruff hint
            k
            for k, v in kwargs.items()
            if v is MISSING
        ]
        if missing:
            raise ConfigError(f"missing values for {missing} for environment '{env}'")

        obj = cls(**kwargs)
        obj._options = options
        obj._section = {} if env == DEFAULT else dict(section)
        obj._default_section = dict(default_section)

        return obj

    def dynamic_config(self, cfg: dict) -> Self:
        if self._options is None or self._section is None or self._default_section is None:
            obj = replace(self, **cfg)
        else:
            kwargs = self._resolve_kwargs(
                options=self._options,
                section=self._section,
                default_section=self._default_section,
                dynamic_config=cfg,
            )
            obj = self.__class__(**kwargs)

        obj._options = self._options
        obj._section = self._section
        obj._default_section = self._default_section

        return obj

    @classmethod
    def _resolve_kwargs(
        cls,
        options: Mapping[str, str],
        section: Mapping[str, str],
        default_section: Mapping[str, str],
        dynamic_config: Optional[Mapping[str, str]] = None,
    ) -> dict[str, str]:
        def _get_value(key: str, default=None):
            if (val := options.get(key)) is not None:
                return val
            if (val := section.get(key)) is not None:
                return val
            if dynamic_config and (val := dynamic_config.get(key)) is not None:
                return val
            if (val := default_section.get(key)) is not None:
                return val

            return default

        return {
            # ruff hint
            field.name: _get_value(field.name, default=field.default)
            for field in fields(cls)
            if not field.name.startswith("_")
        }


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
        return get_queue_name(self.stack_name, self.cnm_ingest_queue)

    def cnm_response_queue_name(self) -> str:
        return get_queue_name(self.stack_name, self.cnm_response_queue)


def get_queue_name(stack_name: Optional[str], queue_name: str) -> str:
    if stack_name and not queue_name.startswith(stack_name):
        return f"{stack_name}-{queue_name}"

    return queue_name
