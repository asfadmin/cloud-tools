import logging
import os

from cnm_sender import CnmSender

log = logging.getLogger(__name__)


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
            logging.Formatter("%(asctime)s %(levelname)s %(name)s %(filename)s:%(lineno)d - %(message)s")
        )


def load_test():
    c_sender = CnmSender({})
    c_sender.send()


def lambda_handler(event, context):
    configure_logging()

    log.info(
        "Starting CNM sender invocation",
        extra={
            "aws_request_id": getattr(context, "aws_request_id", None),
        },
    )

    try:
        log.debug("Received event: %s", event)

        load_test()

        log.info("CNM sender invocation completed")
        return {"ok": True}

    except Exception:
        log.exception("CNM sender invocation failed")
        raise


if __name__ == "__main__":
    configure_logging()
    lambda_handler({}, {})
