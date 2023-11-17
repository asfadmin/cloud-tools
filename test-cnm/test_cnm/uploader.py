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
        checksums: Checksums
    ):
        self.session = session
        self.bucket = bucket
        self.checksums = checksums

    def upload_file(
        self,
        path: Path,
        collection: Optional[str] = None,
        product: Optional[str] = None,
    ):
        client = self.session.client("s3")

        md5 = hashlib.md5()
        key = _get_s3_object_key(path, collection, product)

        with open(path, "rb") as f:
            log.debug("Uploading %s to s3://%s/%s", path, self.bucket, key)
            client.upload_fileobj(
                Fileobj=ChecksumReaderProxy(f, md5),
                Bucket=self.bucket,
                Key=key,
            )

        log.debug("Checksum for %s: %s", path, md5.hexdigest())

        self.checksums[key] = md5.hexdigest()


def _get_s3_object_key(
    path: Path,
    collection: Optional[str] = None,
    product: Optional[str] = None,
) -> str:
    collection = collection or path.parent.name
    if not collection:
        raise Exception("Collection name couldn't be determined!")

    if not collection.isupper():
        raise Exception(
            f"Collection name '{collection}' should be uppercase!"
        )

    product = product or path.stem

    return f"{collection}/{product}/{path.name}"
