import argparse
import hashlib
import logging
from typing import List

from test_cnm.checksums import CHECKSUM_PATTERN, Checksums, ChecksumWriter
from test_cnm.config import Config

log = logging.getLogger(__name__)


def add_parser(
    subparsers: argparse._SubParsersAction,
) -> argparse.ArgumentParser:
    parser_update_checksums = subparsers.add_parser(
        "update-checksums",
        help="Update checksums file by downloading products from the bucket",
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

            log.info("Computing checksum for s3://%s/%s", bucket, key)

            md5 = hashlib.md5()
            client.download_fileobj(
                Fileobj=ChecksumWriter(md5),
                Bucket=bucket,
                Key=key,
            )
            md5sum = md5.hexdigest()
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
                        "Computed checksum for s3://%s/%s did not match etag %s",
                        bucket,
                        key,
                        etag_md5sum,
                    )

            checksums[key] = md5sum

    checksums.save()
