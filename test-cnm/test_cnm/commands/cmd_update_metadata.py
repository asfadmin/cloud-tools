import argparse
import hashlib
import json
import logging
from pathlib import Path
from typing import Any, Optional

import boto3
from test_cnm.config import ConfigBasic
from test_cnm.metadata import CHECKSUM_PATTERN, Metadata
from test_cnm.uploader import ChecksumWriter

log = logging.getLogger(__name__)


def add_parser(
    subparsers: argparse._SubParsersAction,
) -> argparse.ArgumentParser:
    parser_update_metadata = subparsers.add_parser(
        "update-metadata",
        help=(
            "Update metadata file for existing products. Checksums can be "
            "parsed from a CNM message or calculated by downloading the file."
        ),
    )
    parser_update_metadata.add_argument(
        "--cnm-file",
        help="Path to a JSON file containing one or more CNM messages to read checksum values from",
        type=Path,
    )
    parser_update_metadata.add_argument(
        "--interactive",
        "-i",
        help="Prompt for unknown values interactively on stdin",
        action="store_true",
    )
    parser_update_metadata.add_argument(
        "--include-property",
        "-p",
        help="Property to update",
        choices=list(PropertyUpdater.PROPERTY_HANDLERS.keys()),
        default=[],
        action="append",
    )
    parser_update_metadata.add_argument(
        "--exclude-property",
        "-x",
        help="Property to ignore when updating",
        choices=list(PropertyUpdater.PROPERTY_HANDLERS.keys()),
        default=[],
        action="append",
    )
    parser_update_metadata.add_argument(
        "prefix",
        help="Prefix to filter keys by",
        nargs="*",
        default=[],
    )
    parser_update_metadata.set_defaults(
        func=cmd_update_metadata,
        config_cls=ConfigBasic,
    )

    return parser_update_metadata


def cmd_update_metadata(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
    config: ConfigBasic,
):
    prefixes: list[str] = args.prefix

    session = config.session()

    cnm_file = None
    if args.cnm_file:
        with open(args.cnm_file) as f:
            cnm_file = json.load(f)

    with Metadata(session, config.test_bucket) as metadata:
        client = session.client("s3")
        paginator = client.get_paginator("list_objects_v2")

        updater = PropertyUpdater(
            client,
            metadata,
            interactive=args.interactive,
            include_properties=args.include_property,
            exclude_properties=args.exclude_property,
        )

        for response in paginator.paginate(Bucket=config.test_bucket):
            bucket = response["Name"]
            for entry in response.get("Contents", ()):
                key = entry["Key"]

                if (prefixes and not any(key.startswith(prefix) for prefix in prefixes)) or key == metadata.key:
                    continue

                cnm_file_obj = _find_matching_cnm_file_obj(cnm_file, key)

                updater.update_properties(cnm_file_obj, bucket, entry)


class ValueNotFound(Exception):
    pass


class PropertyHandler:
    @staticmethod
    def get_default_value() -> str:
        return "null"

    def get_value_from_cnm_file(
        self,
        property: str,
        cnm_file_obj: dict,
        bucket: str,
        key: str,
    ) -> Any:
        val = cnm_file_obj[property]
        log.info(
            "Using %s from CNM file for s3://%s/%s",
            property,
            bucket,
            key,
        )
        return val

    def get_value_interactively(
        self,
        property: str,
        key: str,
        old_value: Any,
    ) -> Optional[str]:
        return _prompt_with_options(
            f"{property} for {Path(key).name}",
            [],
            old_value,
        )

    def get_value_from_s3(
        self,
        property: str,
        client: boto3.client,
        bucket: str,
        key: str,
    ) -> Any:
        raise ValueNotFound()

    def validate_new_value(self, new_value: Any, bucket: str, entry: dict):
        pass


class ChecksumPropertyHandler(PropertyHandler):
    @staticmethod
    def get_default_value() -> str:
        return "..."

    def get_value_fron_cnm_file(
        self,
        property: str,
        cnm_file_obj: dict,
        bucket: str,
        key: str,
    ) -> Any:
        del property

        checksum_type = cnm_file_obj.get("checksumType")
        checksum = cnm_file_obj["checksum"]

        if checksum_type and checksum_type != "md5":
            log.debug(
                "Skipping checksum %s for s3://%s/%s because it has type %s",
                checksum,
                bucket,
                key,
                checksum_type,
            )
            raise ValueNotFound()
        else:
            log.info(
                "Using checksum from CNM file for s3://%s/%s",
                bucket,
                key,
            )
            return checksum

    def get_value_from_s3(
        self,
        property: str,
        client: boto3.client,
        bucket: str,
        key: str,
    ) -> str:
        del property

        log.info("Computing checksum for s3://%s/%s", bucket, key)

        md5 = hashlib.md5()
        client.download_fileobj(
            Fileobj=ChecksumWriter(md5),
            Bucket=bucket,
            Key=key,
        )
        return md5.hexdigest()

    def validate_new_value(self, new_value: Any, bucket: str, entry: dict):
        key = entry["Key"]
        m = CHECKSUM_PATTERN.match(entry["ETag"])
        if m:
            etag_md5sum = m.group(1)
            if etag_md5sum != new_value:
                log.warning(
                    "Computed checksum for s3://%s/%s did not match etag [computed: %s, etag: %s]",
                    bucket,
                    key,
                    new_value,
                    etag_md5sum,
                )


class TypePropertyHandler(PropertyHandler):
    def get_value_interactively(
        self,
        property: str,
        key: str,
        old_value: Any,
    ) -> Optional[str]:
        del property

        if old_value is None:
            old_value = "null"

        valid_types = ["data", "metadata", "browse", "qa", "linkage", "null"]
        while True:
            new_value = _prompt_with_options(
                f"type for {Path(key).name}",
                valid_types,
                old_value,
            )
            if new_value not in valid_types:
                confirm = input(
                    f"{repr(new_value)} should be one of {repr(valid_types)}. Are you sure? [y/N]: ",
                ).strip()
                if confirm.lower() != "y":
                    continue

            break

        if new_value == "null":
            return None

        return new_value


class PropertyUpdater:
    PROPERTY_HANDLERS = {
        "checksum": ChecksumPropertyHandler(),
        "type": TypePropertyHandler(),
    }

    def __init__(
        self,
        client: boto3.client,
        metadata: Metadata,
        interactive: bool = False,
        include_properties: list[str] = [],
        exclude_properties: list[str] = [],
    ):
        self.client = client
        self.metadata = metadata

        self.interactive = interactive
        self.include_properties = include_properties
        self.exclude_properties = exclude_properties

    def update_properties(
        self,
        cnm_file_obj: Optional[dict],
        bucket: str,
        entry: dict,
    ):
        for property, handler in self.PROPERTY_HANDLERS.items():
            if self.is_enabled(property):
                self.update_property(
                    property,
                    cnm_file_obj,
                    bucket,
                    entry,
                    handler,
                )

    def update_property(
        self,
        property: str,
        cnm_file_obj: Optional[dict],
        bucket: str,
        entry: dict,
        handler: PropertyHandler,
    ):
        key = entry["Key"]

        old_value = None
        if key in self.metadata:
            metadata_entry = self.metadata[key]
            if property in metadata_entry:
                old_value = metadata_entry[property]

        new_value = self.get_value_from_handler(
            property,
            handler,
            cnm_file_obj,
            bucket,
            key,
            old_value,
        )
        if new_value is None or new_value == old_value:
            log.debug(
                "Skipping %s for s3://%s/%s %s",
                property,
                bucket,
                key,
                old_value,
            )
            return

        log.debug(
            "Updating %s for s3://%s/%s %s -> %s",
            property,
            bucket,
            key,
            old_value if old_value is not None else handler.get_default_value(),
            new_value,
        )

        if new_value is not None:
            self.metadata[key][property] = new_value
        else:
            self.metadata.delete(key, property)

        handler.validate_new_value(new_value, bucket, entry)

    def get_value_from_handler(
        self,
        property: str,
        handler: PropertyHandler,
        cnm_file_obj: Optional[dict],
        bucket: str,
        key: str,
        old_value: Any,
    ) -> Any:
        if cnm_file_obj and property in cnm_file_obj:
            try:
                return handler.get_value_from_cnm_file(
                    property,
                    cnm_file_obj,
                    bucket,
                    key,
                )
            except ValueNotFound:
                pass

        if self.interactive:
            try:
                return handler.get_value_interactively(
                    property,
                    key,
                    old_value,
                )
            except ValueNotFound:
                pass

        try:
            return handler.get_value_from_s3(
                property,
                self.client,
                bucket,
                key,
            )
        except ValueNotFound:
            pass

    def is_enabled(self, property: str) -> bool:
        if self.include_properties and property not in self.include_properties:
            return False

        if property in self.exclude_properties:
            return False

        return True


def _prompt_with_options(
    prompt: str,
    valid_options: list[str],
    default: Optional[str] = None,
) -> Optional[str]:
    options = []
    for option in valid_options:
        first = option[0]
        if option == default:
            first = first.upper()

        options.append(f"({first}){option[1:]}")

    if default is not None and default not in valid_options:
        options.append(f"default={default}")

    options_text = "/".join(options)
    val = input(f"{prompt} [{options_text}]: ").strip()
    if not val:
        return default

    for typ in valid_options:
        if typ.startswith(val):
            return typ

    return val


def _find_matching_cnm_file_obj(cnm_file: Any, key: str) -> Optional[dict]:
    if isinstance(cnm_file, dict) and "files" in cnm_file:
        files = cnm_file["files"]
        if isinstance(files, list):
            for file in files:
                if isinstance(file, dict):
                    name = file.get("name")
                    if name and key.endswith(name):
                        return file

    if isinstance(cnm_file, dict):
        for obj in cnm_file.values():
            file = _find_matching_cnm_file_obj(obj, key)
            if file:
                return file

    elif isinstance(cnm_file, list):
        for obj in cnm_file:
            file = _find_matching_cnm_file_obj(obj, key)
            if file:
                return file

    return None
