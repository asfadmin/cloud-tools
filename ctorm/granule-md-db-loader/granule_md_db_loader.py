import os
import sys
import gzip
import json
import logging
import datetime
from decimal import Decimal
import boto3

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


def main():
    bucket_name = os.environ.get("CTORM_BUCKET", "ctorm-scratch")
    table_name = os.environ.get("TABLE_NAME")
    prefix = os.environ.get("PREFIX", "cumulus-granules/")

    if not table_name:
        logger.error("TABLE_NAME environment variable is required.")
        sys.exit(1)

    s3 = boto3.client("s3")
    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(table_name)

    logger.info(f"Starting import from s3://{bucket_name}/{prefix} into DynamoDB table {table_name}")

    paginator = s3.get_paginator("list_objects_v2")
    pages = paginator.paginate(Bucket=bucket_name, Prefix=prefix)

    total_files = 0
    total_records = 0

    # Walk through the bucket objects
    for page in pages:
        if "Contents" not in page:
            continue

        for obj in page["Contents"]:
            key = obj["Key"]
            if not key.endswith(".jsonl.gz"):
                continue

            logger.info(f"Processing s3://{bucket_name}/{key}")
            total_files += 1

            # Download and decompress the file
            local_path = "/tmp/temp.jsonl.gz"
            try:
                s3.download_file(bucket_name, key, local_path)
            except Exception as e:
                logger.error(f"Failed to download s3://{bucket_name}/{key}: {e}")
                continue

            # Open, decompress and parse
            records_in_file = 0
            try:
                with gzip.open(local_path, "rt", encoding="utf-8") as f:
                    with table.batch_writer() as batch:
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue

                            try:
                                # Convert floats/doubles to Decimal for DynamoDB compatibility
                                item = json.loads(line, parse_float=Decimal)
                            except Exception as e:
                                logger.error(f"Failed to parse JSON line: {e}")
                                continue

                            # Add/modify fields if needed
                            # Example additional fields:
                            item["imported_at"] = datetime.datetime.utcnow().isoformat() + "Z"

                            # Ensure partition and sort keys are present
                            if "pk" not in item or "sk" not in item:
                                logger.warning(f"Skipping record missing pk/sk: {item.get('granule_id')}")
                                continue

                            # Batch insert into DynamoDB
                            batch.put_item(Item=item)
                            records_in_file += 1
                            total_records += 1

                logger.info(f"Successfully imported {records_in_file} records from {key}")
            except Exception as e:
                logger.error(f"Error processing file {key}: {e}")
            finally:
                if os.path.exists(local_path):
                    os.remove(local_path)

    logger.info(f"Import complete. Processed {total_files} files, imported {total_records} total records.")


if __name__ == "__main__":
    main()
