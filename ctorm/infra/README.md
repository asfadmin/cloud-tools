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
