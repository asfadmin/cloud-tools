import base64
import gzip
import json
import logging
import os
import tomllib
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Optional

import boto3
from boto3.dynamodb.types import TypeDeserializer
from cnm import CtormCnmSGenerator, CtormGranuleRow

MAX_MSG_SIZE = 262144
MAX_BATCH_SIZE = 1048576
BATCH_PADDING = 130000

fmt = "%(asctime)s [%(levelname)s] %(message)s"
logging.basicConfig(level=logging.DEBUG, format=fmt)
log = logging.getLogger(__name__)


def decimal_begone(obj: Any):
    if isinstance(obj, Decimal):
        # Convert to int if whole number, otherwise float
        return int(obj) if obj % 1 == 0 else float(obj)
    return obj


@dataclass
class PrepSqsMsgCollectionCfg:
    collection_name: str
    num_of_granules: int
    start_date: int
    end_date: int


@dataclass
class PrepSqsCfg:
    dyndb_tablename: str
    granule_goal: int
    maturity: str
    sqs_queue_url: str

    msg_collections: list[dict]


class PrepSqsMsgCollection:
    table = None

    def __init__(self, cfg: dict, table):
        self.cfg = PrepSqsMsgCollectionCfg(**cfg)

        self.table = table
        self.deserializer = TypeDeserializer()
        self.cnm_s_generator = CtormCnmSGenerator()
        self.current_date = self.cfg.start_date
        self.excl_start_key: dict = {}

    def get_pk(self):
        return f"{self.cfg.collection_name}#{self.current_date}"

    def get_query_params(self, num_of_granules: Optional[int] = None):
        if not num_of_granules:
            num_of_granules = self.cfg.num_of_granules
        qp = {
            "KeyConditionExpression": "pk = :pk_val",
            "ExpressionAttributeValues": {":pk_val": self.get_pk()},
            "Limit": num_of_granules,
        }
        if self.excl_start_key:
            qp["ExclusiveStartKey"] = self.excl_start_key
        # log.debug("Query params: %s", qp)
        return qp

    def increment_curr_date(self):
        mm = str(self.current_date)[4:6]
        if mm == "12":
            yyyy = str(self.current_date)[0:4]
            mm = "01"
            yyyy = str(int(yyyy) + 1)
            self.current_date = int(yyyy + mm)
        else:
            self.current_date += 1
        # we get a validation error if we don't reset this.
        self.excl_start_key = {}
        if self.current_date > self.cfg.end_date:
            raise Exception("Reached end date. TODO: what to do?")

    def _set_excl_start_key(self, resp):
        self.excl_start_key = resp.get("LastEvaluatedKey", {})

    def query_dyndb(self, num_of_granules: int):
        # log.debug("Querying dyndb for %d granules", num_of_granules)
        response = self.table.query(**self.get_query_params(num_of_granules))
        self._set_excl_start_key(response)
        if response.get("Count", 0) < num_of_granules:
            self.increment_curr_date()

        # Let's get rid of the decimal type.
        for row in response["Items"]:
            for fi in row.get("f", {}):
                fi.update({k: decimal_begone(v) for k, v in fi.items()})
            row.update({k: decimal_begone(v) for k, v in row.items()})
        return response["Items"]

    def get_msg_list(self):
        msg_list = []
        while len(msg_list) < self.cfg.num_of_granules:
            items = self.query_dyndb(self.cfg.num_of_granules - len(msg_list))
            for item in items:
                msg_list.append(self.convert_dyndb_item_to_cnm(item))
        return msg_list

    def convert_dyndb_item_to_cnm(self, item: dict):
        return self.cnm_s_generator(CtormGranuleRow(**item))


def package_msg(msgs: list) -> tuple:
    json_bytes = json.dumps(msgs).encode("utf-8")
    b64_str = base64.b64encode(gzip.compress(json_bytes)).decode("utf-8")
    msg_id = str(uuid.uuid4())
    ATTRIBUTE_SIZE = 32
    msg_size = len(b64_str.encode("utf-8") + msg_id.encode("utf-8")) + ATTRIBUTE_SIZE

    log.debug(
        "b64_str size: %s, %d%% of maximum",
        msg_size,
        round(msg_size / MAX_MSG_SIZE * 100),
    )
    if msg_size > MAX_MSG_SIZE:
        raise Exception("Message too large")
    log.debug("msg_package: `%s...%s`", b64_str[0:20], b64_str[-10:])

    outdict = {
        "Id": msg_id,  # Must be unique within the batch
        "MessageBody": b64_str,
        "MessageAttributes": {
            "ContentEncoding": {"DataType": "String", "StringValue": "gzip+base64"}
        },
    }
    return outdict, msg_size


def do_sqs_send(sqs_client, queue_url, entries):
    if len(entries) == 0:
        return True
    response = sqs_client.send_message_batch(QueueUrl=queue_url, Entries=entries)
    return len(response.get("Successful", [])) == len(entries)


def main():
    with open(os.getenv("PREPARE_SQS_CFG_FILE", "config.toml"), "rb") as f:
        cfg = tomllib.load(f).get("ctorm")
        cfg = PrepSqsCfg(**cfg)

    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(cfg.dyndb_tablename)
    sqs = boto3.client("sqs")
    sqs.set_queue_attributes(
        QueueUrl=cfg.sqs_queue_url,
        Attributes={"MaximumMessageSize": str(MAX_BATCH_SIZE)},
    )

    collections = []
    for coll in cfg.msg_collections:
        collections.append(PrepSqsMsgCollection(coll, table))

    tot_granules = 0
    batch_size = 0
    package_list = []
    while tot_granules < cfg.granule_goal:
        msg_list = []

        for collection in collections:
            item_list = collection.get_msg_list()

            tot_granules += len(item_list)
            msg_list.extend(item_list)

        if len(msg_list) == 0:
            log.info("No more granules to send")
            break

        msg_pkg, msg_size = package_msg(msg_list)
        batch_size += msg_size
        package_list.append(msg_pkg)
        if len(package_list) == 10 or batch_size > (MAX_BATCH_SIZE - BATCH_PADDING):
            log.debug(
                "Sending batch of %d messages, batch size: %d, %d%% of max",
                len(package_list),
                batch_size,
                int((batch_size / MAX_BATCH_SIZE) * 100),
            )
            result = do_sqs_send(sqs, cfg.sqs_queue_url, package_list)
            log.debug("SQS result: %s", result)
            package_list = []
            batch_size = 0

    if len(package_list) > 0:
        # We'll send the last odd batch
        result = do_sqs_send(sqs, cfg.sqs_queue_url, package_list)
        log.debug("SQS result: %s", result)
    log.info("Done sending messages")
    log.info("Total granules: %d", tot_granules)


if __name__ == "__main__":
    boto3_logger = logging.getLogger("boto3")
    botocore_logger = logging.getLogger("botocore")
    urllib3_logger = logging.getLogger("urllib3")
    s3transfer_logger = logging.getLogger("s3transfer")

    boto3_logger.setLevel(logging.WARNING)
    botocore_logger.setLevel(logging.WARNING)
    urllib3_logger.setLevel(logging.WARNING)
    s3transfer_logger.setLevel(logging.WARNING)
    main()
