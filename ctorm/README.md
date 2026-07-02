# CTORM

Cumulus Throughput... uh... ORM?

Load tester tool for Cumulus.

Operates as these steps:

```mermaid
graph TD;
    a[granules in prod cumulus RDS] --> A(cumulus-db-md-extract queries RDS, creates .jsonl files and uploads to S3);
    A -->|  | B[.jsonl files in UAT S3];
    B --> |  | C(granule-md-db-loader reads .jsonl files from S3, loads them into CTORM granules dynamo db);
    C -->| | D[Granules in UAT DynamoDB];
    D -->| | E(prepare-sqs queries the DynamoDB for granules of the specified proportions and creates SQS messages);
    E -->| | F[Granules in UAT SQS];
    F -->| | G(Eventbridge feeds SQS messages to CTORM lambda);
    G -->| | H(CTORM lambda creates CNM and submits them to ingest SQSes);

%% --- LEGEND START ---
subgraph Legend [" "]
    direction LR
    L1[Data Residing]
    L2(Action)
end

classDef dataresides fill:#614c14,stroke:#2231a8,color:#ffffff
classDef actupondata fill:#2231a8,stroke:#614c14,color:#ffffff
class a,B,D,F,L1 dataresides
class A,C,E,G,H,L2 actupondata
style Legend fill:#e6e6e6,stroke:#b5b5b5,color:#333333
```

* cumulus-db-md-extract
    * Operates in the prod account.
    * Gets the metadata from the cumulus database and writes it to a bunch of .jsonl files in a S3 bucket in the
      operational account.
* granule-md-db-loader
    * Operates in the account in which the load test will operate.
    * Reads the .jsonl files from the S3 bucket and loads them into the CTORM granules dynamo db.
