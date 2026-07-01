# CTORM infrastructure

```bash
export AWS_PROFILE="cumulus-sbx-7522"
export VARFILE=dev.tfvars

# create workspaces and select the one to use
terraform workspace new ctorm-dev

terraform workspace new ctorm-prod 

export TF_WORKSPACE=ctorm-dev

terraform init

terraform plan \
  -var-file="${VARFILE}"

terraform apply \
  -var-file="${VARFILE}"
  
terraform destroy  
```

## Increasing DynamoDB table capacity

For loading the DynamoDB table with the .jsonl files, we'll need to increase the capacity of the table.
AWS will throttle drastically if we don't. There is some limitation on how often we can switch between
PROVISIONED and PAY_PER_REQUEST, so don't do it willy-nilly.

```bash
# For temporary use while loading granule metadata:
terraform plan \
  -var-file="${VARFILE}" \
  -var="granule_table_billing_mode=PROVISIONED" \
  -var="granule_table_write_capacity=5000"
  
# To set it back to the default:
terraform plan \
  -var-file="${VARFILE}"
  
  
terraform destroy


```
