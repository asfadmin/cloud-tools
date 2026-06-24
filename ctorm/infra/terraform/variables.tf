
variable "aws_profile" {
  type        = string
  description = "The named AWS profile to use for authentication"
}

variable "name_prefix" {
  type    = string
  default = "ctorm"
}

variable "cumulus_ingest_queue_arn" {
  type        = string
  description = "ARN of the target Cumulus ingest SQS queue."
}

variable "cumulus_ingest_queue_url" {
  type        = string
  description = "URL of the target Cumulus ingest SQS queue."
}

variable "prepare_source_bucket_names" {
  type        = list(string)
  description = "S3 bucket names that ctorm prepare is allowed to read from."
  default = [
    "asf-cumulus-dev-opera-products",
    "asf-cumulus-prod-opera-products",
    "asf-cumulus-test-opera-products",
    "sds-n-cumulus-dev-nisar-products",
    "sds-n-cumulus-prod-nisar-products",
    "sds-n-cumulus-test-nisar-products",
  ]
}

# variable "cumulus_db_md_extract_remote_codebuild_role_arn" {
#   type        = string
#   description = "CodeBuild service role ARN from the remote/RDS account."
# }
