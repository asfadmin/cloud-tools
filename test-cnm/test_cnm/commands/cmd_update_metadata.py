import argparse
import hashlib
import json
import logging
from pathlib import Path
from typing import Optional

from test_cnm.config import ConfigBasic
from test_cnm.metadata import CHECKSUM_PATTERN, ChecksumWriter, Metadata

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
        help=(
            "Path to a JSON file containing one or more CNM messages to read "
            "checksum values from"
        ),
        type=Path,
    )
    parser_update_metadata.add_argument(
        "--skip-type",
        help="Do not update the 'type' field for files",
        action="store_true",
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

        for response in paginator.paginate(Bucket=config.test_bucket):
            bucket = response["Name"]
            for entry in response.get("Contents", ()):
                key = entry["Key"]

                if (
                    prefixes
                    and not any(key.startswith(prefix) for prefix in prefixes)
                ) or key == metadata.key:
                    continue

                cnm_file_obj = _find_matching_cnm_file_obj(cnm_file, key)

                md5sum = update_property(
                    metadata,
                    "checksum",
                    bucket,
                    key,
                    "...",
                    lambda _: get_md5sum(client, cnm_file_obj, bucket, key),
                )

                m = CHECKSUM_PATTERN.match(entry["ETag"])
                if m:
                    etag_md5sum = m.group(1)
                    if etag_md5sum != md5sum:
                        log.warning(
                            "Computed checksum for s3://%s/%s did not match "
                            "etag [computed: %s, etag: %s]",
                            bucket,
                            key,
                            md5sum,
                            etag_md5sum,
                        )

                if not args.skip_type:
                    update_property(
                        metadata,
                        "type",
                        bucket,
                        key,
                        "null",
                        lambda old_value: get_type(cnm_file_obj, bucket, key, old_value),
                    )


def update_property(
    metadata: Metadata,
    property: str,
    bucket: str,
    key: str,
    old_value: str,
    get_value,
):
    if key in metadata:
        entry = metadata[key]
        if property in entry:
            old_value = entry[property]

    new_value = get_value(old_value)

    log.debug(
        "Updating %s for s3://%s/%s %s -> %s",
        property,
        bucket,
        key,
        old_value,
        new_value,
    )

    if new_value is not None:
        metadata[key][property] = new_value
    else:
        metadata.delete(key, property)

    return new_value


def get_md5sum(client, cnm_file_obj, bucket: str, key: str) -> str:
    if cnm_file_obj and "checksum" in cnm_file_obj:
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
        else:
            log.info(
                "Using checksum from CNM file for s3://%s/%s",
                bucket,
                key,
            )
            return checksum

    log.info("Computing checksum for s3://%s/%s", bucket, key)

    md5 = hashlib.md5()
    client.download_fileobj(
        Fileobj=ChecksumWriter(md5),
        Bucket=bucket,
        Key=key,
    )
    return md5.hexdigest()


def get_type(cnm_file_obj, bucket: str, key: str, old_value: str) -> Optional[str]:
    if cnm_file_obj and "type" in cnm_file_obj:
        cnm_type = cnm_file_obj["type"]
        log.info(
            "Using type from CNM file for s3://%s/%s",
            bucket,
            key,
        )
        return cnm_type

    valid_types = ["data", "metadata", "browse", "qa", "linkage", "null"]
    while True:
        new_value = _prompt_with_options(
            f"type for {Path(key).name}",
            valid_types,
            old_value,
        )
        if new_value not in valid_types:
            confirm = input(
                f"{repr(new_value)} should be one of {repr(valid_types)}. "
                "Are you sure? [y/N]: ",
            ).strip()
            if confirm.lower() != "y":
                continue

        break

    if new_value == "null":
        return None

    return new_value


def _prompt_with_options(prompt: str, valid_options: list[str], default: str) -> str:
    options = []
    for option in valid_options:
        first = option[0]
        if option == default:
            first = first.upper()

        options.append(f"({first}){option[1:]}")

    if default not in valid_options:
        options.append(f"default={default}")

    options_text = "/".join(options)
    val = input(f"{prompt} [{options_text}]: ").strip()
    if not val:
        return default

    for typ in valid_options:
        if typ.startswith(val):
            return typ

    return val


def _find_matching_cnm_file_obj(cnm_file, key: str):
    if isinstance(cnm_file, dict) and "files" in cnm_file:
        files = cnm_file["files"]
        if isinstance(files, list):
            for file in files:
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
