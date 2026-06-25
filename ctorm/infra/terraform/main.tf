locals {
  lambda_name = "${var.name_prefix}-cnm-sender"
}


resource "aws_sqs_queue" "granules_dlq" {
  name = "${var.name_prefix}-granule-dlq"
}

resource "aws_sqs_queue" "granules" {
  name                       = "${var.name_prefix}-granules"
  visibility_timeout_seconds = 180

  redrive_policy = jsonencode({
    deadLetterTargetArn = aws_sqs_queue.granules_dlq.arn
    maxReceiveCount     = 5
  })
}

resource "aws_dynamodb_table" "state" {
  name         = "${var.name_prefix}-state"
  billing_mode = "PAY_PER_REQUEST"

  hash_key  = "pk"
  range_key = "sk"

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }
}


resource "aws_cloudwatch_log_group" "cnm-sender" {
  name              = "/aws/lambda/${local.lambda_name}"
  retention_in_days = 14
}

data "aws_iam_policy_document" "lambda_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "cnm-sender" {
  name               = "${var.name_prefix}-cnm-sender-role"
  assume_role_policy = data.aws_iam_policy_document.lambda_assume_role.json
}

data "aws_iam_policy_document" "cnm-sender" {
  statement {
    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents"
    ]

    resources = [
      "${aws_cloudwatch_log_group.cnm-sender.arn}:*"
    ]
  }

  statement {
    actions = [
      "sqs:ReceiveMessage",
      "sqs:DeleteMessage",
      "sqs:GetQueueAttributes"
    ]

    resources = [
      aws_sqs_queue.granules.arn
    ]
  }

  statement {
    actions = [
      "sqs:SendMessage",
      "sqs:SendMessageBatch"
    ]

    resources = [
      var.cumulus_ingest_queue_arn
    ]
  }

  statement {
    actions = [
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:UpdateItem",
      "dynamodb:Query"
    ]

    resources = [
      aws_dynamodb_table.state.arn
    ]
  }
}

resource "aws_iam_role_policy" "cnm-sender" {
  name   = "${var.name_prefix}-cnm-sender-policy"
  role   = aws_iam_role.cnm-sender.id
  policy = data.aws_iam_policy_document.cnm-sender.json
}

data "archive_file" "placeholder_lambda" {
  type        = "zip"
  output_path = "${path.module}/placeholder-lambda.zip"

  source {
    filename = "index.py"

    content = <<EOF
import json
import os

def lambda_handler(event, context):
    print(json.dumps({
        "event": event,
        "granules_queue_url": os.environ.get("GRANULES_QUEUE_URL"),
        "table_name": os.environ.get("TABLE_NAME"),
        "cumulus_ingest_queue_url": os.environ.get("CUMULUS_INGEST_QUEUE_URL"),
    }))

    return {
        "ok": True
    }
EOF
  }
}

resource "aws_lambda_function" "cnm-sender" {
  function_name = local.lambda_name
  role          = aws_iam_role.cnm-sender.arn
  runtime       = "python3.12"
  handler       = "load_tester.lambda_handler"

  filename         = data.archive_file.placeholder_lambda.output_path
  source_code_hash = data.archive_file.placeholder_lambda.output_base64sha256

  timeout     = 120
  memory_size = 512

  environment {
    variables = {
      GRANULES_QUEUE_URL       = aws_sqs_queue.granules.url
      TABLE_NAME               = aws_dynamodb_table.state.name
      CUMULUS_INGEST_QUEUE_URL = var.cumulus_ingest_queue_url
      LOG_LEVEL                = "INFO"
    }
  }

  depends_on = [
    aws_iam_role_policy.cnm-sender,
    aws_cloudwatch_log_group.cnm-sender
  ]
}

resource "aws_cloudwatch_event_rule" "every_minute" {
  name                = "${var.name_prefix}-every-minute"
  schedule_expression = "rate(1 minute)"
  state               = "DISABLED"
}

resource "aws_cloudwatch_event_target" "cnm-sender" {
  rule = aws_cloudwatch_event_rule.every_minute.name
  arn  = aws_lambda_function.cnm-sender.arn

  input = jsonencode({
    source = "eventbridge"
  })
}

resource "aws_lambda_permission" "allow_eventbridge" {
  statement_id  = "AllowExecutionFromEventBridge"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.cnm-sender.function_name
  principal     = "events.amazonaws.com"
  source_arn    = aws_cloudwatch_event_rule.every_minute.arn
}


data "aws_iam_policy_document" "prepare_ec2_assume_role" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "prepare_ec2" {
  name               = "${var.name_prefix}-prepare-ec2-role"
  assume_role_policy = data.aws_iam_policy_document.prepare_ec2_assume_role.json
}

data "aws_iam_policy_document" "prepare_ec2" {
  statement {
    actions = [
      "sqs:SendMessage",
      "sqs:GetQueueAttributes"
    ]

    resources = [
      aws_sqs_queue.granules.arn
    ]
  }

  statement {
    actions = [
      "s3:ListBucket"
    ]

    resources = [
      for bucket_name in var.prepare_source_bucket_names : "arn:aws:s3:::${bucket_name}"
    ]
  }

  statement {
    actions = [
      "s3:GetObject"
    ]

    resources = [
      for bucket_name in var.prepare_source_bucket_names : "arn:aws:s3:::${bucket_name}/*"
    ]
  }
}

resource "aws_iam_role_policy" "prepare_ec2" {
  name   = "${var.name_prefix}-prepare-ec2-policy"
  role   = aws_iam_role.prepare_ec2.id
  policy = data.aws_iam_policy_document.prepare_ec2.json
}

resource "aws_iam_instance_profile" "prepare_ec2" {
  name = "${var.name_prefix}-prepare-ec2-profile"
  role = aws_iam_role.prepare_ec2.name
}



resource "aws_s3_bucket" "scratch" {
  bucket = "${var.name_prefix}-scratch"

  tags = {
    Name = "${var.name_prefix}-scratch"
  }
}

data "aws_iam_policy_document" "allow_scratch_bucket_access" {
  statement {
    actions = [
      "s3:PutObject",
      "s3:GetObject",
      "s3:ListBucket",
      "s3:DeleteObject"
    ]

    resources = [
      aws_s3_bucket.scratch.arn,
      "${aws_s3_bucket.scratch.arn}/*"
    ]
  }
}

resource "aws_iam_role_policy" "scratch_bucket_access" {
  name   = "${var.name_prefix}-scratch-access"
  role   = aws_iam_role.cnm-sender.id # assumes this role already exists
  policy = data.aws_iam_policy_document.allow_scratch_bucket_access.json
}


data "aws_iam_policy_document" "cumulus_db_md_extract_upload_assume_role" {
  statement {
    effect = "Allow"

    actions = [
      "sts:AssumeRole",
    ]

    principals {
      type = "AWS"

      identifiers = [
        "arn:aws:iam::725875338589:root",
        "arn:aws:iam::871271927522:root",
        "arn:aws:iam::372059463218:root",
        "arn:aws:iam::097260566921:root",
        "arn:aws:iam::082931748743:root",
        "arn:aws:iam::510296831643:root"
      ]
    }

    condition {
      test     = "ArnLike"
      variable = "aws:PrincipalArn"

      values = [
        "arn:aws:iam::725875338589:role/ctorm-cumulus-db-md-extract-role",
        "arn:aws:iam::725875338589:role/ctorm-*-cumulus-db-md-extract-role",

        "arn:aws:iam::871271927522:role/ctorm-cumulus-db-md-extract-role",
        "arn:aws:iam::871271927522:role/ctorm-*-cumulus-db-md-extract-role",

        "arn:aws:iam::372059463218:role/ctorm-cumulus-db-md-extract-role",
        "arn:aws:iam::372059463218:role/ctorm-*-cumulus-db-md-extract-role",

        "arn:aws:iam::097260566921:role/ctorm-cumulus-db-md-extract-role",
        "arn:aws:iam::097260566921:role/ctorm-*-cumulus-db-md-extract-role",

        "arn:aws:iam::082931748743:role/ctorm-cumulus-db-md-extract-role",
        "arn:aws:iam::082931748743:role/ctorm-*-cumulus-db-md-extract-role",

        "arn:aws:iam::510296831643:role/ctorm-cumulus-db-md-extract-role",
        "arn:aws:iam::510296831643:role/ctorm-*-cumulus-db-md-extract-role"
      ]
    }
  }
}

resource "aws_iam_role" "cumulus_db_md_extract_upload" {
  name               = "${var.name_prefix}-cumulus-db-md-extract-upload"
  assume_role_policy = data.aws_iam_policy_document.cumulus_db_md_extract_upload_assume_role.json
}

data "aws_iam_policy_document" "cumulus_db_md_extract_upload" {
  statement {
    sid    = "UploadExtractedGranules"
    effect = "Allow"

    actions = [
      "s3:PutObject",
      "s3:AbortMultipartUpload",
    ]

    resources = [
      "${aws_s3_bucket.scratch.arn}/cumulus-granules/*",
    ]
  }

  statement {
    sid    = "ListDestinationPrefix"
    effect = "Allow"

    actions = [
      "s3:ListBucket",
    ]

    resources = [
      aws_s3_bucket.scratch.arn,
    ]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"

      values = [
        "cumulus-granules/*",
      ]
    }
  }
}

resource "aws_iam_role_policy" "cumulus_db_md_extract_upload" {
  name   = "${var.name_prefix}-cumulus-db-md-extract-upload"
  role   = aws_iam_role.cumulus_db_md_extract_upload.id
  policy = data.aws_iam_policy_document.cumulus_db_md_extract_upload.json
}
