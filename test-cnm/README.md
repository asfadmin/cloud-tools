# Test CNM
An End-to-End testing tool for CNM based ingest systems.

This tool is used to send sample CNM-S messages to queue and wait for the
corresponding CNM-R message to be posted to the mock response queue and then
display any errors that occurred.

It also includes some subcommands to help manage the bucket where the sample
data resides.

## Test bucket
The source data is pulled from a bucket containing the files to be sent in the
test payloads. The layout of the bucket is as follows:

```
COLLECTION_1/PRODUCT_1/file1.txt
COLLECTION_1/PRODUCT_1/file2.txt
COLLECTION_1/PRODUCT_1/file3.txt
COLLECTION_2/ARBITRARILY/MANY/SLASHES/PRODUCT_2/file1.txt
COLLECTION_2/ARBITRARILY/MANY/SLASHES/PRODUCT_2/file2.txt
COLLECTION_2/ARBITRARILY/MANY/SLASHES/PRODUCT_2/file3.txt
metadata.json
```

There can be arbitrarily many slashes between the collection name and the
product name in the S3 keys. The script will ignore the intermediate sections
for the purposes of grouping test files together into one payload.

### Metadata file
Generating CNM-S messages requires some additional metadata that isn't
necessarily available on the S3 objects themselves. This metadata can instead be
stored in the `metadata.json` file. Entries in the file are considered optional
and the tool will attempt to guess at the correct values if they are missing
from the metadata file.

The `metadata.json` file is layed out like this:

```json
{
  "COLLECTION_1/PRODUCT_1/file1.txt": {
    "checksum": "00000000000000000000000000000000"
  },
  "COLLECTION_1/PRODUCT_1/file2.txt": {
    "checksum": "00000000000000000000000000000000",
    "type": "linkage"
  }
}
```

Each S3 object key maps to a set of metadata corresponding to keys in the CNM
`product.files` list.

Management of the `metadata.json` file is done through the `upload` and
`update-metadata` commands for convenience. See the `--help` output of each
respective command for usage information.

#### Checksums
For files that are uploaded entirely in a single request, the etag returned by
the s3 ListObjectsV2 operation will be used as the checksum value in the CNM
payload. However, as some files may be large enough that they need to be
uploaded using multipart, the checksums can be set in the `metadata.json` file.

#### Types
By default, the CNM file type designation will be guessed based on the file
extension. Possible values for the type are `data`, `metadata`, `browse`,
`linkage`, and `qa`. In cases where the guessed file types are not correct, they
can be overridden in the `metadata.json` file.

## Config
Config variables are read from a `testcnm.cfg` file. First the current
directory is checked and then the user's home directory is checked. Values set
in the current directory will take precedence over values set in the home
directory. Every config option can also be overwritten by passing it through
the command line options.

## Environments
Each `testcnm.cfg` config file can define multiple sections. The name of these
sections defines an environment which can then be selected from the command
line using the `--environment` or `-e` option. This can be used to easily
switch between multiple configurations e.g. to test different maturities of the
same project.

## Defaults
If no environment is specified the `default` environment will be used. If a
config value is missing for the currently specified environment, the value will
be pulled from the entry in the `[default]` section of the config instead.

## Adding New Data to the Bucket

- Get the Granule S3 Path
  - For example, with **`granule_name`**=[OPERA_L3_DISP-S1_IW_F21517_VV_20170516T055331Z_20170528T055332Z_v1.0_20260225T005629Z](https://cumulus-dashboard.asf.earthdatacloud.nasa.gov/granules/granule/OPERA_L3_DISP-S1_IW_F21517_VV_20170516T055331Z_20170528T055332Z_v1.0_20260225T005629Z), scroll down to the columns.
  - Combine the `link` with the `bucket`, and it's s3 path is: `s3://<bucket>/<link>`, but you'll remove the last part of the link.
    - i.e: **`input_granule`**=`s3://asf-cumulus-prod-opera-products/OPERA_L3_DISP-S1_V1/OPERA_L3_DISP-S1_IW_F21517_VV_20170516T055331Z_20170528T055332Z_v1.0_20260225T005629Z/`
- Figure out the tcnm bucket/prefix to store it
  - In the same cumulus-dashboard link, copy the `Collection` value. That'll be the `collection/version` prefix. For example, `OPERA_L3_DISP-S1_V1/1` for this link (but remove any spaces).
  - **`tcnm_bucket`**=`s3://asf-cumulus-dev-e2e-tests/OPERA_L3_DISP-S1_V1/1/`
- Upload the data with:
  - `aws s3 cp --recursive <input_granule> <tcnm_bucket>/<granule_name>/`
  - i.e:

    ```bash
    aws s3 cp --recursive \
    s3://asf-cumulus-prod-opera-products/OPERA_L3_DISP-S1_V1/OPERA_L3_DISP-S1_IW_F21517_VV_20170516T055331Z_20170528T055332Z_v1.0_20260225T005629Z/ \
    s3://asf-cumulus-dev-e2e-tests/OPERA_L3_DISP-S1_V1/1/OPERA_L3_DISP-S1_IW_F21517_VV_20170516T055331Z_20170528T055332Z_v1.0_20260225T005629Z/
    ```

  - You'll notice the `*.cmr.json` file won't copy over, that's expected.
  - Now do the same for the browse bucket. In the columns in the dashboard, one is the browse bucket. (The only thing that changes in the above command is the input bucket. In this case, to `asf-cumulus-prod-opera-browse`):

    ```bash
    aws s3 cp --recursive \
    s3://asf-cumulus-prod-opera-browse/OPERA_L3_DISP-S1_V1/OPERA_L3_DISP-S1_IW_F21517_VV_20170516T055331Z_20170528T055332Z_v1.0_20260225T005629Z/ \
    s3://asf-cumulus-dev-e2e-tests/OPERA_L3_DISP-S1_V1/1/OPERA_L3_DISP-S1_IW_F21517_VV_20170516T055331Z_20170528T055332Z_v1.0_20260225T005629Z/
    ```

  - If you synced over any `*.zarr.json.gz` files, delete them.

- If you uploaded through the console directly, or deleted any files from the upload: run `tcnm tidy`. (It doesn't hurt to just run it either).
- Finally, `tcnm update-metadata <collection_name>`
  - ESPECIALLY if you do this with larger collections, run this in CloudShell. It needs to download each file to md5sum it, so locally can take forever.
  - **Note**: `tcnm update-metadata OPERA_L3_DISP-S1_V1/1/OPERA_L3_DISP-S1_IW_F21517_VV_20170516T055331Z_20170528T055332Z_v1.0_20260225T005629Z/` works to *just* update the above.


## Removing Data from the Bucket

- Delete whatever from `s3://asf-cumulus-dev-e2e-tests`
- Run `tcnm tidy`
