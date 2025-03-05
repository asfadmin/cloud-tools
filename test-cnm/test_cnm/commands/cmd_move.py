import argparse
import logging

from test_cnm.checksums import Checksums
from test_cnm.config import ConfigBasic

log = logging.getLogger(__name__)


def add_parser(
    subparsers: argparse._SubParsersAction,
) -> argparse.ArgumentParser:
    parser_move = subparsers.add_parser(
        "move",
        aliases=["mv"],
        help=(
            "Move test products from one prefix to another and update "
            "checksums file"
        ),
    )
    parser_move.add_argument(
        "src",
        help="Prefix to move products from",
    )
    parser_move.add_argument(
        "dst",
        help="Prefix to move products to",
    )
    parser_move.set_defaults(
        func=cmd_move,
        config_cls=ConfigBasic,
    )

    return parser_move


def cmd_move(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
    config: ConfigBasic,
):
    session = config.session()

    checksums = Checksums(session, config.test_bucket)
    checksums.load()

    client = session.client("s3")
    paginator = client.get_paginator("list_objects_v2")

    for response in paginator.paginate(
        Bucket=config.test_bucket,
        Prefix=args.src,
    ):
        bucket = response["Name"]
        for entry in response.get("Contents", ()):
            key = entry["Key"]
            key_stripped = key.removeprefix(args.src)

            dst_key = args.dst + key_stripped
            log.info(
                "Moving %s bytes s3://%s/%s to s3://%s/%s",
                entry["Size"],
                bucket,
                key,
                bucket,
                dst_key,
            )
            if key in checksums:
                md5sum = checksums[key]
                checksums[dst_key] = md5sum
                del checksums[key]
            client.copy({"Bucket": bucket, "Key": key}, bucket, dst_key)
            client.delete_object(Bucket=bucket, Key=key)

    checksums.save()
