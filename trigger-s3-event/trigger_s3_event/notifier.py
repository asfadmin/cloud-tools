import fnmatch
import json
import logging
import pprint
import uuid
from abc import ABC, abstractmethod

import boto3
from trigger_s3_event.template import replace

log = logging.getLogger()


class Notifier(ABC):
    def __init__(
        self,
        client: boto3.client,
        configuration: dict,
        dry_run: bool = False,
    ):
        self.client = client
        self.configuration_id: str = configuration["Id"]
        self.configuration_events: list[str] = configuration["Events"]
        self.configuration_filter: dict = configuration.get("Filter") or {}
        self.dry_run = dry_run

        self._batch_size = 10
        self._current_batch = []

    @abstractmethod
    def send_batch(self, batch: list[dict]):
        pass

    def batched_notify(
        self,
        event_name: str,
        record_template: dict,
        entry: dict,
    ):
        assert len(self._current_batch) < self._batch_size

        if not self.passes_event(event_name):
            return
        if not self.passes_filter_rules(entry):
            return

        self._current_batch.append(
            self.create_record(record_template, entry),
        )

        if len(self._current_batch) == self._batch_size:
            batch, self._current_batch = self._current_batch, []

            self.send_batch(batch)

    def passes_event(self, event_name: str) -> bool:
        return any(
            fnmatch.fnmatchcase(event_name, configuration_event_name)
            for configuration_event_name in self.configuration_events
        )

    def passes_filter_rules(self, entry: dict) -> bool:
        key_name_filter = self.configuration_filter.get("Key")
        if key_name_filter:
            key = entry["Key"]

            for rule in key_name_filter.get("FilterRules", ()):
                name, value = rule["Name"], rule["Value"]

                if name == "Prefix" and not key.startswith(value):
                    return False
                if name == "Suffix" and not key.endswith(value):
                    return False

        return True

    def create_record(self, record_template: dict, entry: dict) -> dict:
        return replace(
            record_template,
            entry=entry,
            configuration_id=self.configuration_id,
        )

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_value, traceback):
        if self._current_batch:
            batch, self._current_batch = self._current_batch, []

            self.send_batch(batch)


class LambdaNotifier(Notifier):
    def __init__(
        self,
        client: boto3.client,
        configuration: dict,
        dry_run: bool = False,
    ):
        super().__init__(client, configuration, dry_run)
        self.arn = configuration["LambdaFunctionArn"]

    def send_batch(self, batch: list[dict]):
        for event in batch:
            if self.dry_run:
                log.info("dryrun: Would invoke lambda: %s", self.arn)
                _pretty_print_entries([event])
            else:
                self.client.invoke(
                    FunctionName=self.arn,
                    InvocationType="Event",
                    Payload=json.dumps(event).encode(),
                )


class SNSTopicNotifier(Notifier):
    def __init__(
        self,
        client: boto3.client,
        configuration: dict,
        dry_run: bool = False,
    ):
        super().__init__(client, configuration, dry_run)
        self.arn = configuration["TopicArn"]

    def send_batch(self, batch: list[dict]):
        entries = [
            {
                "Id": str(uuid.uuid4()),
                "Subject": "Amazon S3 Notification from trigger_s3_event",
                "Message": json.dumps(event),
            }
            for event in batch
        ]
        if self.dry_run:
            log.info("dryrun: Would publish batch to SNS topic: %s", self.arn)
            _pretty_print_entries(entries)
        else:
            self.client.publish_batch(
                TopicArn=self.arn,
                PublishBatchRequestEntries=entries,
            )


class SQSQueueNotifier(Notifier):
    def __init__(
        self,
        client: boto3.client,
        configuration: dict,
        dry_run: bool = False,
    ):
        super().__init__(client, configuration, dry_run)
        self.url = client.get_queue_url(
            QueueName=configuration["QueueArn"].rsplit(":", 1)[1],
        )["QueueUrl"]

    def send_batch(self, batch: list[dict]):
        entries = [
            {
                "Id": str(uuid.uuid4()),
                "MessageBody": json.dumps(event),
            }
            for event in batch
        ]
        if self.dry_run:
            log.info("dryrun: Would publish batch to SQS: %s", self.url)
            _pretty_print_entries(entries)
        else:
            self.client.send_message_batch(
                QueueUrl=self.url,
                Entries=entries,
            )


def _pretty_print_entries(entries: list[dict]):
    pprinter = pprint.PrettyPrinter(sort_dicts=False)
    for entry in entries:
        lines = pprinter.pformat(entry).split("\n")
        for line in lines:
            log.info("dryrun: %s", line)
