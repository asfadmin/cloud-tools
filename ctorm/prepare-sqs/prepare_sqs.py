import base64
import gzip
import json
import logging
import os
import tomllib
from dataclasses import dataclass, fields
from decimal import Decimal
from typing import Optional

import boto3

fmt = "%(asctime)s [%(levelname)s] %(message)s"
logging.basicConfig(level=logging.DEBUG, format=fmt)
log = logging.getLogger(__name__)


class DecimalBegone(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            # Convert to int if whole number, otherwise float
            return int(obj) if obj % 1 == 0 else float(obj)
        return super(DecimalBegone, self).default(obj)


@dataclass
class PrepSqsMsgCollectionCfg:
    collection_name: str
    num_of_granules: int
    start_date: int
    end_date: int


class PrepSqsMsgCollection:
    table = None

    def __init__(self, cfg: dict, table):
        self.cfg = PrepSqsMsgCollectionCfg(**cfg)

        self.table = table

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
        log.debug("Query params: %s", qp)
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
        log.debug("Querying dyndb for %d granules", num_of_granules)
        response = self.table.query(**self.get_query_params(num_of_granules))
        self._set_excl_start_key(response)
        if response.get("Count", 0) < num_of_granules:
            self.increment_curr_date()

        return response.get("Items", [])

    def get_msg_list(self):
        msg_list = []
        while len(msg_list) < self.cfg.num_of_granules:
            items = self.query_dyndb(self.cfg.num_of_granules - len(msg_list))
            for item in items:
                msg_list.append(convert_dyndb_item_to_cnm(item))
        return msg_list


def convert_dyndb_item_to_cnm(item: dict):
    log.debug("TODO: convert dyndb item to cnm")
    return item


def package_msg(msgs: list):
    json_bytes = json.dumps(msgs, cls=DecimalBegone).encode("utf-8")
    b64_str = base64.b64encode(gzip.compress(json_bytes)).decode("utf-8")

    log.debug("b64_str size: %s", len(b64_str))
    if len(b64_str) > 262144:
        raise Exception("Message too large")
    return b64_str


def main():
    with open(os.getenv("PREPARE_SQS_CFG_FILE", "config.toml"), "rb") as f:
        cfg = tomllib.load(f).get("ctorm")
    dynamodb = boto3.resource("dynamodb")
    table = dynamodb.Table(cfg.get("dyndb_tablename"))
    collections = []
    for coll in cfg.get("msg_collections", []):
        collections.append(PrepSqsMsgCollection(coll, table))

    tot_granules = 0
    while tot_granules < cfg.get("granule_goal", 0):
        msg_list = []
        for collection in collections:
            item_list = collection.get_msg_list()

            tot_granules += len(item_list)
            msg_list.extend(item_list)

        msg_package = package_msg(msg_list)
        # TODO: send sqs here.
        log.debug("msg_package: %s...%s", msg_package[0:20], msg_package[-10:])


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
