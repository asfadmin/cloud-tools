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
export AWS_PROFILE="cumulus-uat-6921"
export VARFILE=opera-uat.tfvars
export STATEFILE=terraform-opera-uat.tfstate

terraform workspace new opera-uat

export TF_WORKSPACE=opera-uat

terraform init

terraform plan \
  -state="${STATEFILE}" \
  -var-file="${VARFILE}"

terraform apply \
  -state="${STATEFILE}" \
  -var-file="${VARFILE}"
  
terraform destroy


```

### Codebuild

```bash
export AWS_PROFILE="cumulus-uat-6921"
export AWS_REGION="us-west-2"
export CODEBUILD_PROJECT="$(terraform output -state="${STATEFILE}" -raw cumulus_db_md_extract_codebuild_project_name)"

# You can do one collection at a time, many in parallel if necessary: 
export COLLECTION="OPERA_L2_RTC-S1_V1"

# start build:
BUILD_ID="$(
  aws codebuild start-build \
    --project-name "${CODEBUILD_PROJECT}" \
    --region "${AWS_REGION}" \
    --environment-variables-override name=COLLECTION,value="${COLLECTION}",type=PLAINTEXT \
    --query 'build.id' \
    --output text
)"

echo "${BUILD_ID}"

# Or start build specifying a custom slices.tsv file from S3:
# BUILD_ID="$(
   aws codebuild start-build \
     --project-name "${CODEBUILD_PROJECT}" \
     --region "${AWS_REGION}" \
     --environment-variables-override name=SLICES_S3_URI,value="s3://ctorm-scratch/cumulus-granules/opera/slices_daily-OPERA_L2_CSLC-S1_V1-20180707-20200522.tsv",type=PLAINTEXT  \
     --query 'build.id' \
     --output text
# )"


# get status:
aws codebuild batch-get-builds \
  --ids "${BUILD_ID}" \
  --region "${AWS_REGION}" \
  --query 'builds[0].{status:buildStatus,phase:currentPhase,start:startTime,end:endTime,logs:logs.deepLink}' \
  --output table

# get build logs:
aws codebuild batch-get-builds \
  --ids "${BUILD_ID}" \
  --region "${AWS_REGION}" \
  --query 'builds[0].logs.deepLink' \
  --output text

LOG_GROUP="$(aws codebuild batch-get-builds --ids "${BUILD_ID}" --region "${AWS_REGION}" --query 'builds[0].logs.groupName' --output text)"
LOG_STREAM="$(aws codebuild batch-get-builds --ids "${BUILD_ID}" --region "${AWS_REGION}" --query 'builds[0].logs.streamName' --output text)"

aws logs tail "${LOG_GROUP}" \
  --log-stream-names "${LOG_STREAM}" \
  --follow \
  --region "${AWS_REGION}"

```
