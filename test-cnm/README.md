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
checksums.json
COLLECTION_1/PRODUCT_1/file1.txt
COLLECTION_1/PRODUCT_1/file2.txt
COLLECTION_1/PRODUCT_1/file3.txt
COLLECTION_2/ARBITRARILY/MANY/SLASHES/PRODUCT_2/file1.txt
COLLECTION_2/ARBITRARILY/MANY/SLASHES/PRODUCT_2/file2.txt
COLLECTION_2/ARBITRARILY/MANY/SLASHES/PRODUCT_2/file3.txt
```

There can be arbitrarily many slashes between the collection name and the
product name in the S3 keys. The script will ignore the intermediate sections
for the purposes of grouping test files together into one payload.

### Checksums file
For files that are uploaded entirely in a single request, the etag returned by
the s3 ListObjectsV2 operation will be used as the checksum value in the CNM
payload. However, as some files may be large enough that they need to be
uploaded using multipart, an additional s3 object is used to store the computed
checksums for these large files.

The file has the key `checksums.json` and is layed out like this:

```json
{
  "COLLECTION_1/PRODUCT_1/file1.txt": {
    "checksum": "00000000000000000000000000000000"
  },
  "COLLECTION_1/PRODUCT_1/file2.txt": {
    "checksum": "00000000000000000000000000000000"
  }
}
```

Management of the `checksums.json` file is done through the `upload` and
`update-checksums` commands for convenience. See the `--help` output of each
respective command for usage information.

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
