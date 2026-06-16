import hashlib
import json
import os
import re
from functools import cache
from logging import getLogger

import boto3
from botocore.exceptions import ClientError
from mypy_boto3_s3.type_defs import HeadObjectRequestTypeDef, ListObjectsV2OutputTypeDef

from ctorm.config import CtormBucket, CtormConfig

log = getLogger(__name__)


@cache
def get_boto_session():

    kwargs = {"region_name": AWS_REGION}
    if os.getenv("AWS_ACCESS_KEY_ID") and os.getenv("AWS_SECRET_ACCESS_KEY"):
        kwargs["aws_access_key_id"] = os.getenv("AWS_ACCESS_KEY_ID")
        kwargs["aws_secret_access_key"] = os.getenv("AWS_SECRET_ACCESS_KEY")

    return boto3.Session(**kwargs)


@cache
def get_s3_client():
    return get_boto_session().client("s3", region_name=AWS_REGION)


@cache
def get_sqs_client():
    return get_boto_session().client("sqs", region_name=AWS_REGION)
class CtormSqsMessage:
    MAX_MESSAGE_SIZE = 262144

    def __init__(self, cfg: CtormConfig):
        self.cfg = cfg
        self.files = []

    def add_file(self, file: dict):
        self.files.append(file)

    def to_dict(self):
        return {"files": self.files}

    def to_json(self):
        return json.dumps(self.to_dict())

    def check_message_size(self):
        return len(self.to_json()) < self.MAX_MESSAGE_SIZE


class CtormPrepare:
    MD5_DL_CHUNK_MB = 8

    def __init__(self, cfg: CtormConfig):
        self.cfg = cfg
        self.boto_session = boto3.Session(
            region_name="us-west-2",
            aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
            aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        )
        self.s3_client = self.boto_session.client("s3")
        self.sqs_client = self.boto_session.client("sqs")

    def prepare(self):
        goal = 50
        while goal > 0:  # TODO: replace with while true and an exit condition
            # This is the loop that creates a SQS message from multiple objects.
            sqs_msg = CtormSqsMessage(self.cfg)
            for b in self.cfg.source_buckets:
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
                    ummg = self.download_ummg(b.bucketname, obj["Key"])
                    file = self.process_ummg(ummg, b)
                    if file:
                        sqs_msg.add_file(file)
                    goal -= 1
                b.next_cont_token = page.get("NextContinuationToken")

            log.debug("goal: %d", goal)
            log.debug("sqs_msg size: %d", len(sqs_msg.to_json()))
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

    def get_ummg_page(self, ct_bukt: CtormBucket) -> ListObjectsV2OutputTypeDef:
        kwargs = {
            "Bucket": ct_bukt.bucketname,
            "MaxKeys": ct_bukt.share,
            "Prefix": ct_bukt.ummg_prefix,
        }
        if ct_bukt.next_cont_token:
            kwargs["ContinuationToken"] = ct_bukt.next_cont_token
        ret = get_s3_client().list_objects_v2(**kwargs)
        return ret

    def download_ummg(self, bucketname: str, key: str) -> dict:
        resp = get_s3_client().get_object(Bucket=bucketname, Key=key)
        ummgfile = resp["Body"].read()
        return json.loads(ummgfile)

    def process_ummg(self, ummg: dict, ct_bkt: CtormBucket) -> dict:
        outdict = {
            "bm": {ct_bkt.bucketname: "B1"},  # bucket map
            "g": ummg["GranuleUR"],
            "c": ummg["CollectionReference"]["ShortName"],
            "cv": ummg["CollectionReference"]["Version"],
            "f": [],  # list of files
        }

        for f in ummg["RelatedUrls"]:
            if f["URL"].startswith("s3://"):
                bucket = re.sub(r"^s3://([^/]+).*$", r"\1", f["URL"])
                if bucket != ct_bkt.bucketname:
                    outdict["bm"][bucket] = f"B{len(outdict['bm'])}"
                objloc = f["URL"].removeprefix(f"s3://{bucket}/")

                # Replace the granulename with a token for compression. Will reconstitute in the lambda
                fileval = f["URL"].replace(outdict["g"], "$G").replace(bucket, f"${outdict['bm'][bucket]}")
                filedict = {"f": fileval}
                for m in ummg["DataGranule"]["ArchiveAndDistributionInformation"]:
                    if f["URL"].endswith(m["Name"]):
                        # We handily have the md5 and size in the ummg
                        filedict["m"] = m["Checksum"]["Value"]
                        filedict["s"] = m["SizeInBytes"]
                        break
                    else:
                        # We must look to S3 for the size and md5
                        log.debug('getting head for "%s"', objloc)
                        try:
                            log.debug("head_object: %s", h)
                            filedict["s"] = h["ContentLength"]
                            filedict["m"] = h["ETag"].replace('"', "")
                            if filedict["m"].endswith("-1"):
                            headobj = get_s3_client().head_object(Bucket=bucket, Key=objloc)
                                # This was a multipart upload. We'll have to do something clever to get the MD5 of it.
                                log.debug("multipart upload detected for %s", objloc)
                                filedict["m"] = self.get_real_md5(h, bucket, objloc)
                        except ClientError as e:
                            log.error("head_object failed: %s", e)
                            # TODO: trash entire message for this granule?

                outdict["f"].append(filedict)

        return outdict

    def get_real_md5(
        self,
        head_obj_ret: HeadObjectRequestTypeDef,
        bucket: str,
        key: str,
    ) -> str:
        # The file is small enough we may as well download it to memory and get the MD5 that way.
        resp = get_s3_client().get_object(Bucket=bucket, Key=key)
        md5_accumulator = hashlib.md5()
        for chunk in iter(lambda: resp["Body"].read(self.MD5_DL_CHUNK_MB * 1024 * 1024), b""):
            md5_accumulator.update(chunk)
        return md5_accumulator.hexdigest()
