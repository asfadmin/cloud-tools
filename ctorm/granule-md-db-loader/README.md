# Granule MD DB Loader

## Deploying

The infrastructure for this is provided by the [CTORM terraform](../infra/README.md)

## Before running

AWS throttles writes to dynamo DB if we insert repeatedly into the same partion, so when we can run
multiple collections at once, each going into their own partition.

Additionally, running as PAY_PER_REQUEST will get us throttled no matter what. So for the loading of the granules, we
will switch the tf to use PROVISIONED. See the [CTORM infrastruture README](../infra/README.md) for the command to do
this.

## Running

```bash
# for dev:
export AWS_PROFILE="cumulus-sbx-7522"
export CODEBUILD_PROJECT="ctorm-dev-granule-md-db-loader"
export CTORM_BUCKET="ctorm-dev-scratch"


# get list of collections
aws s3 ls s3://${CTORM_BUCKET}/cumulus-granules/nisar/ |grep PRE
aws s3 ls s3://${CTORM_BUCKET}/cumulus-granules/opera/ |grep PRE

# If you want do them all sequentially, not recommended and not going to work with all the data because throttling::
aws codebuild start-build --profile="${AWS_PROFILE}" \
--project-name "${CODEBUILD_PROJECT}" \
--region "us-west-2" \
--query 'build.id' \
--output text



# Running a specific collection in parallel (by overriding the PREFIX):
aws codebuild start-build --profile="${AWS_PROFILE}" \
--project-name "${CODEBUILD_PROJECT}" \
--region "us-west-2" \
--environment-variables-override name=PREFIX,value=cumulus-granules/opera/OPERA_L2_CSLC-S1_V1_/,type=PLAINTEXT \
--query 'build.id' \
--output text
aws codebuild start-build --profile="${AWS_PROFILE}" \
--project-name "${CODEBUILD_PROJECT}" \
--region "us-west-2" \
--environment-variables-override name=PREFIX,value=cumulus-granules/opera/OPERA_L2_RTC-S1_V1_/,type=PLAINTEXT \
--query 'build.id' \
--output text
aws codebuild start-build --profile="${AWS_PROFILE}" \
--project-name "${CODEBUILD_PROJECT}" \
--region "us-west-2" \
--environment-variables-override name=PREFIX,value=cumulus-granules/opera/OPERA_L3_DISP-S1_V1_/,type=PLAINTEXT \
--query 'build.id' \
--output text
aws codebuild start-build --profile="${AWS_PROFILE}" \
--project-name "${CODEBUILD_PROJECT}" \
--region "us-west-2" \
--environment-variables-override name=PREFIX,value=cumulus-granules/opera/OPERA_L3_DIST-ALERT-S1_V1_/,type=PLAINTEXT \
--query 'build.id' \
--output text
# nisar
aws codebuild start-build --profile="${AWS_PROFILE}" \
--project-name "${CODEBUILD_PROJECT}" \
--region "us-west-2" \
--environment-variables-override name=PREFIX,value=cumulus-granules/nisar/NISAR_EA_L0B_CRSD_/,type=PLAINTEXT \
--query 'build.id' \
--output text
aws codebuild start-build --profile="${AWS_PROFILE}" \
--project-name "${CODEBUILD_PROJECT}" \
--region "us-west-2" \
--environment-variables-override name=PREFIX,value=cumulus-granules/nisar/NISAR_EA_L0B_RRSD_/,type=PLAINTEXT \
--query 'build.id' \
--output text
aws codebuild start-build --profile="${AWS_PROFILE}" \
--project-name "${CODEBUILD_PROJECT}" \
--region "us-west-2" \
--environment-variables-override name=PREFIX,value=cumulus-granules/nisar/NISAR_EA_L1_/,type=PLAINTEXT \
--query 'build.id' \
--output text
aws codebuild start-build --profile="${AWS_PROFILE}" \
--project-name "${CODEBUILD_PROJECT}" \
--region "us-west-2" \
--environment-variables-override name=PREFIX,value=cumulus-granules/nisar/NISAR_EA_L2/,type=PLAINTEXT \
--query 'build.id' \
--output text

```

## After running

Restore the main.tf to its original state with billing_mode set to PAY_PER_REQUEST, etc.
