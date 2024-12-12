# Trigger S3 Event
A tool to send fake S3 event notifications for objects that already exist in a
bucket.

The tool works by reading existing event notification configurations or by
specifying an ARN on the command line along with a number of filters to select
the desired objects. Each matching object is used to generate a fake S3 event
notification that follows the standard S3 event notification format and is
posted to the event notification destination (SNS, SQS, Lambda or EventBridge).
