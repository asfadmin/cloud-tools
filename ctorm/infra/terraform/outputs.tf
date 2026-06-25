output "granules_queue_url" {
  value = aws_sqs_queue.granules.url
}

output "granules_queue_arn" {
  value = aws_sqs_queue.granules.arn
}

output "granules_dlq_url" {
  value = aws_sqs_queue.granules_dlq.url
}

output "granule_table_name" {
  value = aws_dynamodb_table.granules.name
}

output "worker_lambda_name" {
  value = aws_lambda_function.cnm-sender.function_name
}

output "scratch_bucket" {
  value = aws_s3_bucket.scratch.bucket
}

output "cumulus_db_md_extract_upload_role_arn" {
  value = aws_iam_role.cumulus_db_md_extract_upload.arn
}
