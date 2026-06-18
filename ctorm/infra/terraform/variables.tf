
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
