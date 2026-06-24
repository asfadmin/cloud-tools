# Cumulus DB MD Extractor

The purpose of this is to get enough medata from the prod cumulus RDS db and into a Dynamo DB to be able to recreate
CNM-S messages.

# How to use:

## From the web console

* Open a web console from Kion
    * Open a tab with the secrets manager
        * Find the secret with `db_login` in the name. This is where you find the host, user/pass, etc.
    * Open a tab with the RDS
        * Go to the query editor
    * Open a CloudShell in anohter tab.
        * Pick the VPC
        * Pick the same subnet as the RDS
        * Pick the default security group and the one(s) with `_rds_` in the name.
    * TODO: see if we can do this with EC2 instead of cloudshell

## From the shell

### prepare the environment

Create AWS credentials to upload to the CTORM bucket.

```bash
mkdir .aws
vi .aws/credentials

[ctorm]
aws_access_key_id = AKYEAH...
aws_secret_access_key = foofoofooofooo
```

Make some env vars:

```bash

read -s PGPASSWORD
export PGPASSWORD
export PGHOST='from secrets mgr'
export PGUSER='from secrets mgr'
export PGDATABASE='from secrets mgr'

# this is the ctorm bucket and path info where the db dumps are stored
export CTORM_BUCKET='ctorm-dev-scratch'
export DUMP_SUBDIR='nisar'

```

Get these files into the instance one way or another.

* ctorm/cumulus-db-md-extract/export-granules-daily.sh
* ctorm/cumulus-db-md-extract/export-granules-slice-daily.sql
* ctorm/cumulus-db-md-extract/generate-slices-daily.sh

## Run the scripts

```bash
bash generate-slices-daily.sh
```

This creates a `slices_daily.tsv` file. Basically a list of chunked work for export-granules-daily.sh to use.

The following step will query the database and create gzipped ljson files and upload them to S3:

```bash
bash export-granules-daily.sh
```

If running in cloudshell, you need to put some sort of input into the console every 10 minutes or so, or AWS will kill
the session.
Really should try to create a EC2 next time.

## Using Codebuild

### Terraform

```bash
```bash
export AWS_PROFILE="cumulus-uat-6921"
export VARFILE=opera-uat.tfvars
terraform init

terraform plan \
  -var-file="${VARFILE}"

terraform apply \
  -var-file="${VARFILE}"
  
terraform destroy


```

```

```bash
aws codebuild create-project \
    --name "OneTimeDataPull" \
    --source '{"type": "S3", "location": "ctorm-dev-scratch/codebuild/codebuild-noop.zip"}' \
    --environment '{"type": "LINUX_CONTAINER", "image": "aws/codebuild/amazonlinux2-x86_64-standard:5.0", "computeType": "BUILD_GENERAL1_SMALL"}' \
    --artifacts '{"type": "NO_ARTIFACTS"}' \
    --service-role "arn:aws:iam::123456789012:role/service-role/YourCodeBuildRole" \
    --timeout-in-minutes 240
```
