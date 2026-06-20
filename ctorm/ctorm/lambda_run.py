"""
Emulates a lambda for local dev.
"""

import json
import logging

from aws_lambda_typing import context as context_

from ctorm.load_tester import lambda_handler

log = logging.getLogger()

base_fmt_str = "%(levelname)s: %(message)s (%(filename)s line %(lineno)d/)"
screen_fmt = logging.Formatter(
    "%(asctime)s.%(msecs)d " + base_fmt_str, "%Y-%m-%dT%H:%M:%S"
)
screenlog = logging.StreamHandler()
screenlog.setFormatter(screen_fmt)
log.addHandler(screenlog)


# mock event data
with open("../../data/lambda-event-eventbridge.json", "r") as f:
    mock_event = json.load(f)


# Mock context object
class MockContext(context_.Context):
    function_name = "local_test"
    memory_limit_in_mb = 128
    aws_request_id = "LOLOCAL"


# Run it
print(lambda_handler(mock_event, MockContext()))
