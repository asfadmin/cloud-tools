import argparse
import logging

import boto3

log = logging.getLogger(__name__)


def add_parser(
    subparser: argparse._SubParsersAction,
) -> argparse.ArgumentParser:
    parser_test = subparser.add_parser(
        "test",
        help="Run a full end to end event based ingest test"
    )
    parser_test.add_argument(
        "--mission",
        help="name of the mission",
    )
    parser_test.add_argument(
        "--dest-bucket",
        help="Destination S3 bucket",
    )
    parser_test.set_defaults(
        func=cmd_test,
    )


# TODO: Add ConfigFull
def cmd_test(
    parser: argparse.ArgumentParser,
    args: argparse.Namespace,
) -> None:
    session = boto3.Session(profile_name=args.profile)
    s3_client = session.client("s3")
    source_bucket = args.test_bucket
    destination_bucket = args.dest_bucket
    prefix = args.mission.upper()

    paginator = s3_client.get_paginator("list_objects_v2")
    pages = paginator.paginate(Bucket=source_bucket, Prefix=prefix)

    for page in pages:
        for obj in page.get("Contents", []):
            object_key = obj["Key"]
            copy_source = {"Bucket": source_bucket, "Key": object_key}
            log.info(
                "Copying %s to s3://%s/%s",
                object_key,
                destination_bucket,
                object_key,
            )
            s3_client.copy(copy_source, destination_bucket, object_key)
