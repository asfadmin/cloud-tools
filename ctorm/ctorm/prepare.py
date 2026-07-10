import hashlib
import json
import os
import re
from enum import StrEnum
from functools import cache
from logging import getLogger

import boto3
from botocore.exceptions import ClientError
from mypy_boto3_s3.type_defs import ListObjectsV2OutputTypeDef

from ctorm.config import AWS_REGION, MD5_CHECKSUM_PATTERN, CtormConfig, CtormPipeline

log = getLogger(__name__)


@cache
def get_sqs_client():
    return boto3.client("sqs", region_name=AWS_REGION)


class K(StrEnum):
    """Since we want to keep the message json as light as possible, we'll keep
    the keys for the message sent to the CTORM SQS queue here.
    """

    BKT_MAP = "bm"
    GRANULE = "g"
    COLLECTION = "c"
    COLLECTION_VERSION = "cv"
    FILES = "f"
    MD5 = "m"
    SIZE = "s"


class CtormSqsMessage:
    MAX_MESSAGE_SIZE = 262144

    def __init__(self, cfg: CtormConfig):
        self.cfg = cfg
        self.granules = []

    def add_file(self, file: dict):
        self.granules.append(file)

    def to_dict(self):
        return {"granules": self.granules}

    def to_json(self):
        return json.dumps(self.to_dict())

    def check_message_size(self):
        return len(self.to_json()) < self.MAX_MESSAGE_SIZE


class CtormPrepare:
    MD5_DL_CHUNK_MB = 8

    def __init__(self, cfg: CtormConfig):
        self.cfg = cfg
        self.total_granules = 0

        self._boto_sessions = {}

        # init buckets
        for bkt in self.cfg.pipelines:
            bkt.next_cont_token = None
            keysuffix = (
                f"_{bkt.prepare_keypair_name}" if bkt.prepare_keypair_name else ""
            )
            if bkt.prepare_keypair_name not in self._boto_sessions:
                self._boto_sessions[bkt.prepare_keypair_name] = boto3.Session(
                    region_name=AWS_REGION,
                    aws_access_key_id=os.getenv(f"AWS_ACCESS_KEY_ID{keysuffix}"),
                    aws_secret_access_key=os.getenv(
                        f"AWS_SECRET_ACCESS_KEY{keysuffix}"
                    ),
                )
            bkt.s3_client = self._boto_sessions[bkt.prepare_keypair_name].client("s3")

    def prepare(self):
        while self.total_granules < self.cfg.granule_goal:
            # This is the loop that creates a SQS message from multiple objects.
            sqs_msg = CtormSqsMessage(self.cfg)
            for b in self.cfg.pipelines:
                # This is the loop that goes into each bucket we're interested in.
                log.debug("getting objects from %s", b.bucketname)

                # get a page from obj_iterator
                # We want only one page because we want to get only b.share files for this go.
                page = self.get_ummg_page(b)
                for obj in page.get("Contents", []):
                    if not obj["Key"].endswith(".cmr.json"):
                        log.debug("skipping %s", obj["Key"])
                        continue
                    log.debug("  %s", obj["Key"])
                    # download the json object and load it into a var:
                    ummg = self.download_ummg(b, obj["Key"])
                    file = self.process_ummg(ummg, b)
                    if file:
                        sqs_msg.add_file(file)
                    self.total_granules += 1
                b.next_cont_token = page.get("NextContinuationToken")

            log.debug("tot granules: %d/%d", self.total_granules, self.cfg.granule_goal)
            log.debug("sqs_msg size: %d", len(sqs_msg.to_json()))
            log.debug(
                "sqs message percentage: %d%%",
                (len(sqs_msg.to_json()) / CtormSqsMessage.MAX_MESSAGE_SIZE) * 100,
            )
            log.debug("sqs_msg size OK?: %d", sqs_msg.check_message_size())
            if sqs_msg.check_message_size():
                log.debug("sqs_msg: %s", sqs_msg.to_json())
                get_sqs_client().send_message(
                    QueueUrl=self.cfg.granules_sqs_queue_url,
                    MessageBody=sqs_msg.to_json(),
                )
            else:
                raise Exception("Message too big")
                # TODO: deal with this smarter

    def get_ummg_page(self, ct_bukt: CtormPipeline) -> ListObjectsV2OutputTypeDef:
        kwargs = {
            "Bucket": ct_bukt.bucketname,
            "MaxKeys": ct_bukt.share,
            "Prefix": ct_bukt.ummg_prefix,
        }
        if ct_bukt.next_cont_token:
            kwargs["ContinuationToken"] = ct_bukt.next_cont_token
        ret = ct_bukt.s3_client.list_objects_v2(**kwargs)
        return ret

    def download_ummg(self, b: CtormPipeline, key: str) -> dict:
        resp = b.s3_client.get_object(Bucket=b.bucketname, Key=key)
        ummgfile = resp["Body"].read()
        return json.loads(ummgfile)

    def process_ummg(self, ummg: dict, ct_bkt: CtormPipeline) -> dict:
        outdict = {
            K.BKT_MAP: {ct_bkt.bucketname: "B1"},  # bucket map
            K.GRANULE: ummg["GranuleUR"],
            K.COLLECTION: ummg["CollectionReference"]["ShortName"],
            K.COLLECTION_VERSION: ummg["CollectionReference"]["Version"],
            K.FILES: [],  # list of files
        }

        for r_urls in ummg["RelatedUrls"]:
            if r_urls["URL"].startswith("s3://"):
                bucket = re.sub(r"^s3://([^/]+).*$", r"\1", r_urls["URL"])
                if bucket != ct_bkt.bucketname:
                    outdict[K.BKT_MAP][bucket] = f"B{len(outdict[K.BKT_MAP])}"
                objloc = r_urls["URL"].removeprefix(f"s3://{bucket}/")

                # Replace the granulename with a token for compression. Will reconstitute in the lambda
                fileval = (
                    r_urls["URL"]
                    .replace(outdict[K.GRANULE], "$G")
                    .replace(bucket, f"${outdict[K.BKT_MAP][bucket]}")
                )
                filedict = {"f": fileval}
                for distr_file in ummg["DataGranule"][
                    "ArchiveAndDistributionInformation"
                ]:
                    if r_urls["URL"].endswith(distr_file["Name"]):
                        # We handily have the md5 and size in the ummg
                        # TODO: double-check this test is correct and we're not unnecessarily HEADing too many files.
                        filedict[K.SIZE] = distr_file["SizeInBytes"]
                        filedict[K.MD5] = distr_file["Checksum"]["Value"]
                        break
                    else:
                        # We must look to S3 for the size and md5
                        log.debug('getting head for "%s"', objloc)
                        try:
                            headobj = ct_bkt.s3_client.head_object(
                                Bucket=bucket, Key=objloc
                            )
                            log.debug("head_object: %s", headobj)
                            filedict[K.SIZE] = headobj["ContentLength"]

                            md5 = headobj["ETag"].replace('"', "")
                            if MD5_CHECKSUM_PATTERN.fullmatch(md5):
                                filedict[K.MD5] = md5
                            elif self.cfg.calc_md5:
                                log.debug("multipart upload detected for %s", objloc)
                                filedict[K.MD5] = self.get_real_md5(
                                    ct_bkt, bucket, objloc
                                )
                            else:
                                log.debug("no need to calculate md5 for %s", objloc)
                        except ClientError as e:
                            log.error("head_object failed: %s", e)
                            # TODO: trash entire message for this granule?

                outdict[K.FILES].append(filedict)

        return outdict

    def get_real_md5(
        self,
        b: CtormPipeline,
        obj_bucket: str,
        key: str,
    ) -> str:
        # The file is small enough we may as well download it to memory and get the MD5 that way.
        resp = b.s3_client.get_object(Bucket=obj_bucket, Key=key)
        md5_accumulator = hashlib.md5()
        for chunk in iter(
            lambda: resp["Body"].read(self.MD5_DL_CHUNK_MB * 1024 * 1024), b""
        ):
            md5_accumulator.update(chunk)
        return md5_accumulator.hexdigest()
