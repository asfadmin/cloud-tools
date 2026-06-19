"""
Emulates a lambda for local dev.
"""

import json

from ctorm.load_tester import lambda_handler

# mock event data
with open("../../data/lambda_event.json", "r") as f:
    mock_event = json.load(f)


# Mock context object
class MockContext:
    function_name = "local_test"
    memory_limit_in_mb = 128


# Run it
print(lambda_handler(mock_event, MockContext()))
