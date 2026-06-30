import datetime
import gzip
import json
import logging
import os
import random
import sys
import time
from decimal import Decimal

import boto3
from botocore.config import Config

# Configure logging
fmt = "%(asctime)s [%(levelname)s] %(message)s"
logging.basicConfig(level=logging.INFO, format=fmt)
log = logging.getLogger(__name__)


class PartitionRateLimiter:
    """
    Limits the number of write requests to any single partition key (pk)
    to prevent exceeding DynamoDB's physical limit of 1000 operations/sec per partition.
    """

    def __init__(self, max_rate_per_sec: int = 890):
        self.max_rate = max_rate_per_sec
        self.history = {}  # pk -> list of timestamps

    def limit(self, pk):
        now = time.time()
        if pk not in self.history:
            self.history[pk] = []

        # Retain only timestamps from the last 1.0 second
        self.history[pk] = [t for t in self.history[pk] if now - t < 1.0]

        if len(self.history[pk]) >= self.max_rate:
            # Calculate sleep duration to let the oldest request roll
            # off the 1-second window
            sleep_time = 1.0 - (now - self.history[pk][0])
            if sleep_time > 0:
                time.sleep(sleep_time)
            now = time.time()
            self.history[pk] = [t for t in self.history[pk] if now - t < 1.0]

        self.history[pk].append(now)


def handle_file(
    local_path: str,
    table,
    rate_limiter: PartitionRateLimiter,
    records_in_file: int,
    total_records: int,
):
    with (
        gzip.open(local_path, "rt", encoding="utf-8") as f,
        table.batch_writer() as batch,
    ):
        for line in f:
            line = line.strip()
            if not line:
                continue

            try:
                # Convert floats/doubles to Decimal for
                # DynamoDB compatibility
                item = json.loads(line, parse_float=Decimal)
            except Exception as e:
                log.error("Failed to parse JSON line: %s", e)
                continue

            # Add/modify fields if needed
            newdate = datetime.datetime.now(datetime.timezone.utc).isoformat() + "Z"
            item["imported_at"] = newdate

            # Ensure partition and sort keys are present
            pk = item.get("pk")
            sk = item.get("sk")
            if not pk or not sk:
                log.warning(
                    "Skipping record missing pk/sk: %s",
                    item.get("granule_id"),
                )

                continue

            # Apply dynamic rate limit based on the partition key
            rate_limiter.limit(pk)

            # Batch insert into DynamoDB
            batch.put_item(Item=item)
            records_in_file += 1
            total_records += 1
    return records_in_file, total_records


def main():
    bucket_name = os.environ.get("CTORM_BUCKET", "ctorm-scratch")
    table_name = os.environ.get("TABLE_NAME")
    prefix = os.environ.get("PREFIX", "cumulus-granules/")

    if not table_name:
        log.error("TABLE_NAME environment variable is required.")
        sys.exit(1)

    s3 = boto3.client("s3")

    # Configure boto3 with more aggressive retries to gracefully
    # handle scale peaks
    retry_config = Config(
        retries={
            "max_attempts": 10,
            "mode": "standard",
        }
    )
    dynamodb = boto3.resource("dynamodb", config=retry_config)
    dyndb_table = dynamodb.Table(table_name)

    log.info(
        "Starting import from s3://%s/%s into DynamoDB table %s",
        bucket_name,
        prefix,
        table_name,
    )

    paginator = s3.get_paginator("list_objects_v2")
    pages = paginator.paginate(Bucket=bucket_name, Prefix=prefix)

    total_files = 0
    total_records = 0

    # Initialize partition-level rate limiter set to a safe
    # threshold (850 writes/sec per pk)
    rate_limiter = PartitionRateLimiter(max_rate_per_sec=850)

    # create random list of .json.gz objects:
    # This will alleviate writing to the same partition for several files in a row.
    jsongz_list = []
    for page in pages:
        if "Contents" not in page:
            continue
        for obj in page["Contents"]:
            key = obj["Key"]
            if not key.endswith(".jsonl.gz"):
                continue
            jsongz_list.append(key)
            total_files += 1

    total_files = len(jsongz_list)
    random.shuffle(jsongz_list)

    # Walk through the bucket objects
    for key in jsongz_list:
        log.info("Processing s3://%s/%s", bucket_name, key)

        # Download and decompress the file
        local_path = "/tmp/temp.jsonl.gz"
        try:
            s3.download_file(bucket_name, key, local_path)
        except Exception as e:
            log.error(
                "Failed to download s3://{%s}/%s: %s",
                bucket_name,
                key,
                e,
            )
            continue

        # Open, decompress and parse
        records_in_file = 0
        try:
            records_in_file, total_records = handle_file(
                local_path,
                dyndb_table,
                rate_limiter,
                records_in_file,
                total_records,
            )

            log.info(
                "Successfully imported %s records from %s",
                records_in_file,
                key,
            )
        except Exception as e:
            log.error("Error processing file %s: %s", key, e)
        finally:
            if os.path.exists(local_path):
                os.remove(local_path)

    log.info(
        "Import complete. Processed %s files, imported %s total records.",
        total_files,
        total_records,
    )


if __name__ == "__main__":
    main()
