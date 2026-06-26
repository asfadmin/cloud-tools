# Granule MD DB Loader

## Deploying

The infrastructure for this is provided by the [CTORM terraform](../infra/README.md)

## Running

```bash
# for dev:
export AWS_PROFILE="cumulus-sbx-7522"
export CODEBUILD_PROJECT="ctorm-dev-granule-md-db-loader"

aws codebuild start-build --profile="${AWS_PROFILE}" \
--project-name "${CODEBUILD_PROJECT}" \
--region "us-west-2" \
--query 'build.id' \
--output text

```
