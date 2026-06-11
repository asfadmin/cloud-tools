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
