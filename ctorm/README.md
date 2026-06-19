# CTORM
Cumulus Throughput... uh... ORM?

Load tester tool for Cumulus.

Operates as two steps:

* Prepare
    * The prepare step goes through the UMMG directory of specified prod buckets and
      extracts the metadata necessary to recreate CNM messages. It then creates SQS messages
      containing lists of these metadata.
* CNM Sender
    * The CNM Sender step reads the SQS messages and sends them to the Cumulus ingest queue.

## Prepare

### Cfg file

See the `ctorm.cfg.example` file.

#### source_buckets

| key          | value                                                     |
|--------------|-----------------------------------------------------------|
| bucketname   | Name of bucket in which to find the UMMG files            |
| keypair_name | Arbritrary name to suffix to the AWS keypair env var      |
| share        | Number of granules from this collection to add to the CNM |
| ummg_prefix  | Path in bucketname where to find the desired UMMG files   |

Let's say you have the following source buckets set up:

### Env vars

You will need to have the following environment variables set:

* `AWS_ACCESS_KEY_ID_[keypair_name]` where `keypair_name` matches an entry in the ctorm cfg toml file.
* `AWS_SECRET_ACCESS_KEY_[keypair_name]` where `keypair_name` matches an entry in the ctorm cfg toml file.
