import codecs
import io
import json
import logging
import re
from collections import defaultdict

import boto3

log = logging.getLogger(__name__)


CHECKSUM_PATTERN = re.compile(r'^"([\da-f]{32})"$')


class Metadata:
    def __init__(
        self,
        session: boto3.Session,
        bucket: str,
        key: str = "metadata.json",
    ):
        self.session = session
        self.bucket = bucket
        self.key = key
        self.test_config_key = "$testconfig"

        self.metadata = defaultdict(dict)

    @property
    def test_config(self) -> dict:
        return self[self.test_config_key]

    def load(self):
        client = self.session.client("s3")

        log.debug(
            "Loading metadata file from s3://%s/%s",
            self.bucket,
            self.key,
        )

        try:
            with io.BytesIO() as buf:
                client.download_fileobj(
                    Fileobj=buf,
                    Bucket=self.bucket,
                    Key=self.key,
                )
                buf.seek(0)
                self.metadata = defaultdict(dict, json.load(buf))
                self.metadata[self.test_config_key] = defaultdict(
                    dict,
                    self.metadata[self.test_config_key],
                )
        except Exception as e:
            log.error("Failed to load metadata file: %s", e)
            log.debug(
                "Error loading metadata file from s3://%s/%s",
                self.bucket,
                self.key,
                exc_info=True,
            )

    def save(self):
        client = self.session.client("s3")

        log.debug(
            "Saving metadata file to s3://%s/%s",
            self.bucket,
            self.key,
        )

        try:
            if not self[self.test_config_key]:
                del self[self.test_config_key]
            # Json requires a StringIO, but boto3 wants a BytesIO
            StreamWriter = codecs.getwriter("utf-8")

            with io.BytesIO() as buf:
                json.dump(self.metadata, StreamWriter(buf))
                buf.seek(0)
                client.upload_fileobj(
                    Fileobj=buf,
                    Bucket=self.bucket,
                    Key=self.key,
                )
        except Exception as e:
            log.error("Failed to save checksums file: %s", e)
            log.debug(
                "Error saving checksum file to s3://%s/%s",
                self.bucket,
                self.key,
                exc_info=True,
            )

    def delete(self, key: str, item: str):
        entry = self.metadata.get(key)
        if entry is None:
            return

        if item in entry:
            del entry[item]

        if not entry:
            del self.metadata[key]

    def __enter__(self) -> "Metadata":
        self.load()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.save()

    def __contains__(self, key: str) -> bool:
        return key in self.metadata

    def __delitem__(self, key: str):
        del self.metadata[key]

    def __getitem__(self, key: str) -> dict:
        if key == self.test_config_key and key not in self.metadata:
            self.metadata[key] = defaultdict(dict)

        return self.metadata[key]

    def __setitem__(self, key: str, value: dict):
        self.metadata[key] = value
