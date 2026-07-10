
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

variable "granule_table_billing_mode" {
  type        = string
  default     = "PAY_PER_REQUEST"
  description = "Must be either PROVISIONED or PAY_PER_REQUEST"
}

variable "granule_table_write_capacity" {
  type        = number
  default     = 10000
  description = "When billing_mode is PROVISIONED, forces write_capacity/10 physical partition splits immediately. Set to 1000*number of parallel granule_md_db_loader runs."
}

# variable "cumulus_db_md_extract_remote_codebuild_role_arn" {
#   type        = string
#   description = "CodeBuild service role ARN from the remote/RDS account."
# }
