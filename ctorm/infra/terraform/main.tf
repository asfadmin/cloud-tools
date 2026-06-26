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

resource "aws_dynamodb_table" "granules" {
  name         = "${var.name_prefix}-granules"
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

  attribute {
    name = "gsi1pk"
    type = "S"
  }

  attribute {
    name = "gsi1sk"
    type = "S"
  }

  global_secondary_index {
    name            = "gsi1"
    hash_key        = "gsi1pk"
    range_key       = "gsi1sk"
    projection_type = "ALL"
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
      aws_dynamodb_table.granules.arn,
      "${aws_dynamodb_table.granules.arn}/index/*"
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
      TABLE_NAME               = aws_dynamodb_table.granules.name
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


# Granule DynamoDB loader.
data "archive_file" "granule_md_db_loader" {
  type        = "zip"
  source_dir  = "${path.module}/../../granule-md-db-loader"
  output_path = "${path.module}/.terraform/granule-md-db-loader.zip"
}

resource "aws_s3_object" "granule_md_db_loader_source" {
  bucket      = aws_s3_bucket.scratch.bucket
  key         = "codebuild/granule-md-db-loader.zip"
  source      = data.archive_file.granule_md_db_loader.output_path
  source_hash = data.archive_file.granule_md_db_loader.output_base64sha256
}

resource "aws_iam_role" "granule_md_db_loader_role" {
  name = "${var.name_prefix}-codebuild-granule_md_db_loader-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Principal = {
          Service = "codebuild.amazonaws.com"
        }
        Action = "sts:AssumeRole"
      }
    ]
  })
}

resource "aws_iam_role_policy" "codebuild_granule_md_db_loader_role_policy" {
  name = "${var.name_prefix}-codebuild-granule-md-db-loader-role-policy"
  role = aws_iam_role.granule_md_db_loader_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:ListBucket"
        ]
        Resource = [
          aws_s3_bucket.scratch.arn,
          "${aws_s3_bucket.scratch.arn}/*"
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:BatchWriteItem"
        ]
        Resource = [
          aws_dynamodb_table.granules.arn
        ]
      }
    ]
  })
}

resource "aws_codebuild_project" "granule_md_db_loader" {
  name          = "${var.name_prefix}-granule-md-db-loader"
  description   = "Imports granules jsonl.gz files from S3 to DynamoDB"
  service_role  = aws_iam_role.granule_md_db_loader_role.arn
  build_timeout = 480

  artifacts {
    type = "NO_ARTIFACTS"
  }

  source {
    type     = "S3"
    location = "${aws_s3_bucket.scratch.bucket}/${aws_s3_object.granule_md_db_loader_source.key}"
  }

  environment {
    type         = "LINUX_CONTAINER"
    image        = "aws/codebuild/amazonlinux2-x86_64-standard:5.0"
    compute_type = "BUILD_GENERAL1_SMALL"

    environment_variable {
      name  = "CTORM_BUCKET"
      value = aws_s3_bucket.scratch.bucket
    }

    environment_variable {
      name  = "TABLE_NAME"
      value = aws_dynamodb_table.granules.name
    }

    environment_variable {
      name  = "PREFIX"
      value = "cumulus-granules/"
    }
  }
}
