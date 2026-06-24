name_prefix = "ctorm"

db_md_extract_secret_arn = "arn:aws:secretsmanager:us-west-2:<remote-account-id>:secret:<secret-name>"

db_md_extract_vpc_id = "vpc-..."

db_md_extract_subnet_ids = [
  "subnet-...",
  "subnet-...",
]

db_md_extract_security_group_ids = [
  "sg-...",
]

db_md_extract_source_bucket = "<some-bucket-in-remote-account>"

db_md_extract_target_bucket = "ctorm-dev-scratch"

db_md_extract_target_role_arn = "arn:aws:iam::<ctorm-account-id>:role/<ctorm-upload-role-name>"

db_md_extract_dump_subdir = "nisar"
