# CTORM infrastructure

```bash
export VARFILE=dev.tfvars
terraform init

terraform plan \
  -var-file="${VARFILE}"

terraform apply \
  -var-file="${VARFILE}"
  
terraform destroy


```
