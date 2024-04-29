import argparse
import hashlib
import json
import logging
from pathlib import Path
from typing import List

from test_cnm.checksums import CHECKSUM_PATTERN, Checksums, ChecksumWriter
from test_cnm.config import Config

log = logging.getLogger(__name__)


def add_parser(
    subparsers: argparse._SubParsersAction,
) -> argparse.ArgumentParser:
    parser_update_checksums = subparsers.add_parser(
        "update-checksums",
        help=(
            "Update checksums file for existing products. Checksums can be "
            "parsed from a CNM message or calculated by downloading the file."
        ),
    )
    parser_update_checksums.add_argument(
        "--cnm-file",
        help=(
            "Path to a JSON file containing one or more CNM messages to read "
            "checksum values from"
        ),
        type=Path,
    )
    parser_update_checksums.add_argument(
        "prefix",
        help="Prefix to filter keys by",
        nargs="*",
        default=[],
    )
    parser_update_checksums.set_defaults(func=cmd_update_checksums)

    return parser_update_checksums


def cmd_update_checksums(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
    config: Config,
):
    prefixes: List[str] = args.prefix

    session = config.session()

    cnm_file = None
    if args.cnm_file:
        with open(args.cnm_file) as f:
            cnm_file = json.load(f)

    checksums = Checksums(session, config.test_bucket)
    checksums.load()

    client = session.client("s3")
    paginator = client.get_paginator("list_objects_v2")

    for response in paginator.paginate(Bucket=config.test_bucket):
        bucket = response["Name"]
        for entry in response.get("Contents", ()):
            key = entry["Key"]

            if prefixes and not any(
                key.startswith(prefix) for prefix in prefixes
            ):
                continue

            md5sum = get_md5sum(client, cnm_file, bucket, key)
            old_md5sum = "..."

            if key in checksums:
                old_md5sum = checksums[key]

            log.debug(
                "Updating checksum for s3://%s/%s %s -> %s",
                bucket,
                key,
                old_md5sum,
                md5sum,
            )

            m = CHECKSUM_PATTERN.match(entry["ETag"])
            if m:
                etag_md5sum = m.group(1)
                if etag_md5sum != md5sum:
                    log.warning(
                        "Computed checksum for s3://%s/%s did not match etag "
                        "[computed: %s, etag: %s]",
                        bucket,
                        key,
                        md5sum,
                        etag_md5sum,
                    )

            checksums[key] = md5sum

    checksums.save()


def get_md5sum(client, cnm_file, bucket: str, key: str):
    if cnm_file:
        file_obj = _find_matching_cnm_file_obj(cnm_file, key)
        if file_obj and "checksum" in file_obj:
            checksum_type = file_obj.get("checksumType")
            checksum = file_obj["checksum"]

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
