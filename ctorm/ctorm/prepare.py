import json
import os
from logging import getLogger

import boto3
from botocore.paginate import PageIterator, Paginator
from mypy_boto3_s3 import S3Client
from mypy_boto3_s3.type_defs import ListObjectsV2OutputTypeDef

from ctorm.config import CtormBucket, CtormConfig

log = getLogger(__name__)


def get_ummg_page(s3_client: S3Client, b_cfg: CtormBucket) -> ListObjectsV2OutputTypeDef:
    kwargs = {
        "Bucket": b_cfg.bucketname,
        "MaxKeys": b_cfg.share,
        "Prefix": b_cfg.ummg_prefix,
    }
    if b_cfg.next_cont_token:
        kwargs["ContinuationToken"] = b_cfg.next_cont_token
    ret = s3_client.list_objects_v2(**kwargs)
    return ret


def download_ummg(s3_client, bucketname: str, key: str) -> dict:
    resp = s3_client.get_object(Bucket=bucketname, Key=key)
    ummgfile = resp["Body"].read()
    return json.loads(ummgfile)


def process_ummg(ummg: dict) -> dict:
    outdict = {}
    for f in ummg["RelatedUrls"]:
        if f["Type"] == "GET DATA VIA DIRECT ACCESS" and f["Format"] == "HDF5":
            outdict["u"] = f["URL"]
            break

    for f in ummg["DataGranule"]["ArchiveAndDistributionInformation"]:
        if f["Format"] == "HDF5":
            outdict["c"] = f["Checksum"]["Value"]
            break
    if "c" not in outdict and "u" not in outdict:
        log.error("No checksum or URL found for %s", ummg["GranuleUR"])
        outdict = {}
    return outdict


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


def prepare(cfg: CtormConfig):
    boto_session = boto3.Session(
        region_name="us-west-2",
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
    )
    s3_client = boto_session.client("s3")
    sqs_client = boto_session.client("sqs")

    goal = 50
    while goal > 0:  # TODO: replace with while true and an exit condition
        # This is the loop that creates a SQS message from multiple objects.
        sqs_msg = CtormSqsMessage(cfg)
        for b in cfg.source_buckets:
            # This is the loop that goes into each bucket we're interested in.
            log.debug("getting objects from %s", b.bucketname)

            # get a page from obj_iterator
            # We want only one page because we want to get only b.share files for this go.
            page = get_ummg_page(s3_client, b)
            for obj in page.get("Contents", []):
                if not obj["Key"].endswith(".cmr.json"):
                    log.debug("skipping %s", obj["Key"])
                    continue
                log.debug("  %s", obj["Key"])
                # download the json object and load it into a var:
                ummg = download_ummg(s3_client, b.bucketname, obj["Key"])
                file = process_ummg(ummg)
                if file:
                    sqs_msg.add_file(file)
                goal -= 1
            b.next_cont_token = page.get("NextContinuationToken")

        log.debug("goal: %d", goal)
        log.debug("sqs_msg size: %d", len(sqs_msg.to_json()))
        log.debug("sqs_msg size OK?: %d", sqs_msg.check_message_size())
        if sqs_msg.check_message_size():
            log.debug("sqs_msg: %s", sqs_msg.to_json())
            sqs_client.send_message(
                QueueUrl=cfg.granules_sqs_queue_url,
                MessageBody=sqs_msg.to_json(),
            )
        else:
            raise Exception("Message too big")
            # TODO: deal with this smarter
