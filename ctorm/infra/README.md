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
  
# For temporary use while loading granule metadata:
terraform plan \
  -var-file="${VARFILE}" \
  -var="granule_table_billing_mode=PROVISIONED" \
  -var="granule_table_write_capacity=10000"
  
terraform apply \
  -var-file="${VARFILE}" \
  -var="granule_table_billing_mode=PROVISIONED" \
  -var="granule_table_write_capacity=10000"
  
  
terraform destroy


```
