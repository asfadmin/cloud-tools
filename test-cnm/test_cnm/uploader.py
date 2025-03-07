import hashlib
import logging
from pathlib import Path
from typing import Optional

import boto3
from test_cnm.checksums import ChecksumReaderProxy, Checksums

log = logging.getLogger(__name__)


class Uploader:
    def __init__(
        self,
        session: boto3.Session,
        bucket: str,
        checksums: Checksums,
    ):
        self.session = session
        self.bucket = bucket
        self.checksums = checksums

    def upload_file(
        self,
        path: Path,
        collection: str,
        data_version: Optional[str] = None,
        product: Optional[str] = None,
    ):
        client = self.session.client("s3")

        md5 = hashlib.md5()
        key = _get_s3_object_key(path, collection, data_version, product)

        with open(path, "rb") as f:
            log.info("Uploading %s to s3://%s/%s", path, self.bucket, key)
            client.upload_fileobj(
                Fileobj=ChecksumReaderProxy(f, md5),
                Bucket=self.bucket,
                Key=key,
            )

        log.debug("Checksum for %s: %s", path, md5.hexdigest())

        self.checksums[key] = md5.hexdigest()


def _get_s3_object_key(
    path: Path,
    collection: str,
    data_version: Optional[str] = None,
    product: Optional[str] = None,
) -> str:
    if not collection.isupper():
        raise Exception(
            f"Collection name '{collection}' should be uppercase!"
        )

    product = product or path.parent.name
    if not product:
        raise Exception("Product name couldn't be determined!")

    if data_version:
        return f"{collection}/{data_version}/{product}/{path.name}"
    else:
        return f"{collection}/{product}/{path.name}"
