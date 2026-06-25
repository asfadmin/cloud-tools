# codebuild-db-md-extract.tf

variable "name_prefix" {
  type    = string
  default = "ctorm"
}

variable "aws_region" {
  type    = string
  default = "us-west-2"
}

variable "db_md_extract_secret_arn" {
  type        = string
  description = "ARN of the Secrets Manager secret containing host, username, password, and database in the RDS account."
}

variable "db_md_extract_vpc_id" {
  type        = string
  description = "VPC where CodeBuild should run to reach the RDS instance."
}

variable "db_md_extract_subnet_ids" {
  type        = list(string)
  description = "Private subnet IDs that can reach the RDS instance."
}

variable "db_md_extract_security_group_ids" {
  type        = list(string)
  description = "Security group IDs for CodeBuild. These must allow egress to the RDS port and be allowed by the RDS SG."
}

variable "db_md_extract_dump_subdir" {
  type    = string
  default = "nisar"
}

variable "db_md_extract_ctorm_bucket" {
  type        = string
  default     = "ctorm-dev-scratch"
  description = "Destination CTORM S3 bucket for exported dump files."
}

variable "db_md_extract_ctorm_s3_role_arn" {
  type        = string
  description = "Role ARN in the CTORM account that CodeBuild can assume to write exported files."
}

locals {
  db_md_extract_project_name = "${var.name_prefix}-cumulus-db-md-extract"
  db_md_extract_source_key   = "codebuild/cumulus-db-md-extract.zip"
}

resource "aws_s3_bucket" "codebuild_source" {
  bucket        = "${local.db_md_extract_project_name}-source-${substr(data.aws_caller_identity.current.account_id, 8, 4)}"
  force_destroy = true

}

resource "aws_s3_bucket_ownership_controls" "codebuild_source" {
  bucket = aws_s3_bucket.codebuild_source.id

  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "codebuild_source" {
  bucket = aws_s3_bucket.codebuild_source.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

resource "aws_s3_bucket_public_access_block" "codebuild_source" {
  bucket = aws_s3_bucket.codebuild_source.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

data "aws_caller_identity" "current" {}

data "archive_file" "cumulus_db_md_extract" {
  type        = "zip"
  source_dir  = "${path.module}/.."
  output_path = "${path.module}/.terraform/cumulus-db-md-extract.zip"

  excludes = [
    "terraform",
    "terraform/*",
    ".terraform",
    ".terraform/*",
  ]
}

resource "aws_s3_object" "cumulus_db_md_extract_source" {
  bucket      = aws_s3_bucket.codebuild_source.bucket
  key         = local.db_md_extract_source_key
  source      = data.archive_file.cumulus_db_md_extract.output_path
  source_hash = data.archive_file.cumulus_db_md_extract.output_base64sha256
}

data "aws_iam_policy_document" "codebuild_db_md_extract_assume_role" {
  statement {
    effect = "Allow"

    actions = [
      "sts:AssumeRole",
    ]

    principals {
      type = "Service"

      identifiers = [
        "codebuild.amazonaws.com",
      ]
    }
  }
}

resource "aws_iam_role" "codebuild_db_md_extract" {
  name               = "${local.db_md_extract_project_name}-role"
  assume_role_policy = data.aws_iam_policy_document.codebuild_db_md_extract_assume_role.json
}

resource "aws_cloudwatch_log_group" "codebuild_db_md_extract" {
  name              = "/aws/codebuild/${local.db_md_extract_project_name}"
  retention_in_days = 14
}

data "aws_iam_policy_document" "codebuild_db_md_extract" {
  statement {
    sid    = "WriteCodeBuildLogs"
    effect = "Allow"

    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]

    resources = [
      "${aws_cloudwatch_log_group.codebuild_db_md_extract.arn}:*",
    ]
  }

  statement {
    sid    = "ReadBuildSource"
    effect = "Allow"

    actions = [
      "s3:GetObject",
      "s3:GetObjectVersion",
    ]

    resources = [
      "${aws_s3_bucket.codebuild_source.arn}/${local.db_md_extract_source_key}",
    ]
  }

  statement {
    sid    = "ListBuildSourceBucket"
    effect = "Allow"

    actions = [
      "s3:ListBucket",
    ]

    resources = [
      aws_s3_bucket.codebuild_source.arn,
    ]

    condition {
      test     = "StringLike"
      variable = "s3:prefix"

      values = [
        "codebuild/*",
      ]
    }
  }

  statement {
    sid    = "ReadDatabaseSecret"
    effect = "Allow"

    actions = [
      "secretsmanager:GetSecretValue",
      "secretsmanager:DescribeSecret",
    ]

    resources = [
      var.db_md_extract_secret_arn,
    ]
  }

  statement {
    sid    = "AssumeCtormAccountUploadRole"
    effect = "Allow"

    actions = [
      "sts:AssumeRole",
    ]

    resources = [
      var.db_md_extract_ctorm_s3_role_arn,
    ]
  }

  statement {
    sid    = "DescribeNetworkForVpcBuild"
    effect = "Allow"

    actions = [
      "ec2:DescribeDhcpOptions",
      "ec2:DescribeRouteTables",
      "ec2:DescribeSecurityGroups",
      "ec2:DescribeSubnets",
      "ec2:DescribeVpcs",
      "ec2:DescribeNetworkInterfaces",
      "ec2:DeleteNetworkInterface",
      "ec2:CreateNetworkInterface",
    ]

    resources = [
      "*",
    ]
  }

  statement {
    sid    = "CreateCodeBuildNetworkInterfacePermission"
    effect = "Allow"

    actions = [
      "ec2:CreateNetworkInterfacePermission",
    ]

    resources = [
      "arn:aws:ec2:${var.aws_region}:*:network-interface/*",
    ]

    condition {
      test     = "StringEquals"
      variable = "ec2:AuthorizedService"

      values = [
        "codebuild.amazonaws.com",
      ]
    }
  }
}

resource "aws_iam_role_policy" "codebuild_db_md_extract" {
  name   = "${local.db_md_extract_project_name}-policy"
  role   = aws_iam_role.codebuild_db_md_extract.id
  policy = data.aws_iam_policy_document.codebuild_db_md_extract.json
}

resource "aws_codebuild_project" "cumulus_db_md_extract" {
  name          = local.db_md_extract_project_name
  description   = "One-time Cumulus RDS metadata export to CTORM S3"
  service_role  = aws_iam_role.codebuild_db_md_extract.arn
  build_timeout = 480

  artifacts {
    type = "NO_ARTIFACTS"
  }

  source {
    type      = "S3"
    location  = "${aws_s3_bucket.codebuild_source.bucket}/${aws_s3_object.cumulus_db_md_extract_source.key}"
    buildspec = "buildspec.yaml"
  }

  environment {
    type         = "LINUX_CONTAINER"
    image        = "aws/codebuild/amazonlinux2-x86_64-standard:5.0"
    compute_type = "BUILD_GENERAL1_SMALL"

    environment_variable {
      name  = "AWS_DEFAULT_REGION"
      value = var.aws_region
    }

    environment_variable {
      name  = "CTORM_BUCKET"
      value = var.db_md_extract_ctorm_bucket
    }

    environment_variable {
      name  = "DUMP_SUBDIR"
      value = var.db_md_extract_dump_subdir
    }

    environment_variable {
      name  = "DB_SECRET_ARN"
      value = var.db_md_extract_secret_arn
    }

    environment_variable {
      name  = "CTORM_S3_ROLE_ARN"
      value = var.db_md_extract_ctorm_s3_role_arn
    }
  }

  vpc_config {
    vpc_id             = var.db_md_extract_vpc_id
    subnets            = var.db_md_extract_subnet_ids
    security_group_ids = var.db_md_extract_security_group_ids
  }

  logs_config {
    cloudwatch_logs {
      group_name = aws_cloudwatch_log_group.codebuild_db_md_extract.name
      status     = "ENABLED"
    }
  }

  depends_on = [
    aws_iam_role_policy.codebuild_db_md_extract,
    aws_s3_object.cumulus_db_md_extract_source,
  ]
}

output "cumulus_db_md_extract_codebuild_project_name" {
  value = aws_codebuild_project.cumulus_db_md_extract.name
}

output "cumulus_db_md_extract_codebuild_role_arn" {
  value = aws_iam_role.codebuild_db_md_extract.arn
}

output "cumulus_db_md_extract_source_s3_uri" {
  value = "s3://${aws_s3_bucket.codebuild_source.bucket}/${aws_s3_object.cumulus_db_md_extract_source.key}"
}
