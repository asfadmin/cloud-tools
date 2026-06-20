import json
import logging
import os
from functools import cache
from typing import List

import boto3
from aws_lambda_typing import context as context_
from aws_lambda_typing import events
from cnm_sender import CnmSender

from ctorm.config import (
    AWS_REGION,
    CtormConfig,
    CtormPreparedGranule,
)

log = logging.getLogger(__name__)


@cache
def get_sqs_client():
    return boto3.client("sqs", region_name=AWS_REGION)


@cache
def configure_cfg():
    cfg = CtormConfig.from_file(
        cfg_file=os.getenv("CFG_FILE", "./ctorm.cfg"),
    )
    return cfg


def configure_logging() -> None:
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    for noisy_logger_name in ("boto3", "botocore", "urllib3", "s3transfer"):
        logging.getLogger(noisy_logger_name).setLevel(logging.WARNING)

    # AWS Lambda installs a handler before invoking your code. Reuse it instead
    # of adding a new handler on every warm invocation.
    for handler in root_logger.handlers:
        handler.setLevel(level)
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s %(levelname)s %(name)s %(filename)s:%(lineno)d - %(message)s"
            )
        )


def get_granule_list(event: events.EventBridgeEvent) -> List[CtormPreparedGranule]:
    # TODO: Implement
    return []


def load_test(
    cfg: CtormConfig,
    gr_queue_url: str,
):
    # fetch 10 messages from SQS
    messages = []
    while len(messages) < 10:
        # Since we're trying to send x granules per invocation, we will do what we can
        # to get a full load of 10 messages.
        sqs_resp = get_sqs_client().receive_message(
            QueueUrl=gr_queue_url,
            MaxNumberOfMessages=min(10 - len(messages), 10),
            WaitTimeSeconds=5,
            VisibilityTimeout=3600,
        )

        batch = sqs_resp.get("Messages", [])
        if not batch:
            break

        messages.extend(batch)

    for message in sqs_resp.get("Messages", []):
        body = json.loads(message["Body"])
        receipt_handle = message["ReceiptHandle"]
        granule_list = body.get("granules", [])

        c_sender = CnmSender(cfg, granule_list)
        success = c_sender.send_all()
        if success:
            log.debug("Deleting message %s", receipt_handle)
            # TODO: uncomment after some dev'ing
            # get_sqs_client().delete_message(
            #     QueueUrl=gr_queue_url, ReceiptHandle=receipt_handle
            # )


def lambda_handler(event: events.EventBridgeEvent, context: context_.Context):
    configure_logging()
    cfg = configure_cfg()

    log.info(
        "Starting CNM sender invocation",
        extra={
            "aws_request_id": getattr(context, "aws_request_id", None),
        },
    )

    try:
        log.debug("Received event: %s", event)
        # g_list = event["Records"].pop().get("body")
        # g_list = json.loads(g_list).get("granules")

        load_test(cfg, event["granules_queue_url"])

        log.info("CNM sender invocation completed")
        return {"ok": True}

    except Exception:
        log.exception("CNM sender invocation failed")
        raise


if __name__ == "__main__":
    lambda_handler({}, {})
