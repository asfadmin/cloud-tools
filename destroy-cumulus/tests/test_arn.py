from destroy_cumulus import Arn


def test_arn_s3_bucket():
    arn = Arn("arn:aws:s3:::bucket-name")

    assert arn.partition == "aws"
    assert arn.service == "s3"
    assert arn.region == ""
    assert arn.account == ""
    assert arn.type == ""
    assert arn.name == "bucket-name"
    assert arn.id == "bucket-name"
    assert arn.type_id == "s3"


def test_arn_lambda_function():
    arn = Arn(
        "arn:aws:lambda:us-west-2:123456789012:"
        "function:lambda-function-name"
    )

    assert arn.partition == "aws"
    assert arn.service == "lambda"
    assert arn.region == "us-west-2"
    assert arn.account == "123456789012"
    assert arn.type == "function"
    assert arn.name == "lambda-function-name"
    assert arn.id == "lambda-function-name"
    assert arn.type_id == "lambda:function"


def test_arn_dynamodb_table():
    arn = Arn(
        "arn:aws:dynamodb:us-west-2:123456789012:"
        "table/table-name"
    )

    assert arn.partition == "aws"
    assert arn.service == "dynamodb"
    assert arn.region == "us-west-2"
    assert arn.account == "123456789012"
    assert arn.type == "table"
    assert arn.name == "table-name"
    assert arn.id == "table-name"
    assert arn.type_id == "dynamodb:table"


def test_arn_cloudwatch_log_group():
    arn = Arn(
        "arn:aws:logs:us-west-2:123456789012:"
        "log-group:/aws/lambda/lambda-name"
    )

    assert arn.partition == "aws"
    assert arn.service == "logs"
    assert arn.region == "us-west-2"
    assert arn.account == "123456789012"
    assert arn.type == "log-group"
    assert arn.name == "/aws/lambda/lambda-name"
    assert arn.id == "/aws/lambda/lambda-name"
    assert arn.type_id == "logs:log-group"


def test_arn_api_gateway():
    arn = Arn("arn:aws:apigateway:us-west-2::/restapis/d36my9ab58")

    assert arn.partition == "aws"
    assert arn.service == "apigateway"
    assert arn.region == "us-west-2"
    assert arn.account == ""
    assert arn.type == "restapis"
    assert arn.name == "d36my9ab58"
    assert arn.id == "d36my9ab58"
    assert arn.type_id == "apigateway:restapis"


def test_arn_cloudformation():
    arn = Arn(
        "arn:aws:cloudformation:us-west-2:123456789012:"
        "stack/dmsn-cumulus-dev-thin-egress-app/"
        "65d8dd50-df49-11eb-b204-020ba035f82f"
    )

    assert arn.partition == "aws"
    assert arn.service == "cloudformation"
    assert arn.region == "us-west-2"
    assert arn.account == "123456789012"
    assert arn.type == "stack"
    assert arn.name == "dmsn-cumulus-dev-thin-egress-app"
    assert arn.id == "65d8dd50-df49-11eb-b204-020ba035f82f"
    assert arn.type_id == "cloudformation:stack"
