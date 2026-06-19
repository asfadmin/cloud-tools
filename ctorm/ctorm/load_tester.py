import json
import logging
import os
from typing import List

from aws_lambda_typing import context as context_
from aws_lambda_typing import events
from cnm_sender import CnmSender

from ctorm.config import (
    CtormConfig,
    CtormPreparedGranule,
)

log = logging.getLogger(__name__)


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


def load_test(cfg: CtormConfig, granule_list: List[CtormPreparedGranule]):
    c_sender = CnmSender(cfg, granule_list)
    c_sender.send_all()


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
        g_list = event["Records"].pop().get("body")
        g_list = json.loads(g_list).get("granules")
        load_test(cfg, g_list)

        log.info("CNM sender invocation completed")
        return {"ok": True}

    except Exception:
        log.exception("CNM sender invocation failed")
        raise


if __name__ == "__main__":
    lambda_handler({}, {})
