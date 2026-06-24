output "granules_queue_url" {
  value = aws_sqs_queue.granules.url
}

output "granules_queue_arn" {
  value = aws_sqs_queue.granules.arn
}

output "granules_dlq_url" {
  value = aws_sqs_queue.granules_dlq.url
}

output "state_table_name" {
  value = aws_dynamodb_table.state.name
}

output "worker_lambda_name" {
  value = aws_lambda_function.cnm-sender.function_name
}

output "prepare_ec2_instance_profile_name" {
  value = aws_iam_instance_profile.prepare_ec2.name
}

output "prepare_ec2_role_arn" {
  value = aws_iam_role.prepare_ec2.arn
}

output "scratch_bucket" {
  value = aws_s3_bucket.scratch.bucket
}

output "cumulus_db_md_extract_upload_role_arn" {
  value = aws_iam_role.cumulus_db_md_extract_upload.arn
}
