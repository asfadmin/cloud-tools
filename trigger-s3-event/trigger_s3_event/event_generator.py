import contextlib
import logging
from datetime import datetime, timezone
from typing import Optional

import boto3
from trigger_s3_event.entry_filter import EntryFilter
from trigger_s3_event.notifier import Notifier, SNSTopicNotifier, SQSQueueNotifier
from trigger_s3_event.template import FormatValue

log = logging.getLogger(__name__)


class EventGenerator:
    def __init__(
        self,
        session: boto3.Session,
        bucket: str,
        dry_run: bool = False,
    ):
        self.session = session
        self.bucket = bucket
        self.dry_run = dry_run

        self._user_identity: Optional[str] = None
        self._notifiers: Optional[list[Notifier]] = None

    def _init_static_data(self):
        if self._user_identity is None:
            self._init_user_identity()

        if self._notifiers is None:
            self._init_notifiers()

    def _init_user_identity(self):
        client = self.session.client("sts")

        response = client.get_caller_identity()
        self._user_identity = response["UserId"]

    def _init_notifiers(self):
        client = self.session.client("s3")

        response = client.get_bucket_notification_configuration(
            Bucket=self.bucket,
        )

        self._notifiers = []

        if queue_configs := response.get("QueueConfigurations"):
            sqs_client = self.session.client("sqs")
            self._notifiers.extend(
                SQSQueueNotifier(sqs_client, configuration, self.dry_run)
                for configuration in queue_configs
            )

        if response.get("LambdaFunctionConfigurations"):
            log.warning("WARNING: Unhandled Lambda configuration(s)")

        if response.get("EventBridgeConfiguration"):
            log.warning("WARNING: Unhandled EventBridge configuration(s)")

        if topic_configs := response.get("TopicConfigurations"):
            sns_client = self.session.client("sns")
            self._notifiers.extend(
                SNSTopicNotifier(sns_client, configuration, self.dry_run)
                for configuration in topic_configs
            )

    def send_events(
        self,
        event_name: str = "s3:ObjectCreated:Put",
        prefix: str = "",
        entry_filter: Optional[EntryFilter] = None,
        override_notifiers: list[Notifier] = [],
    ):
        self._init_static_data()

        client = self.session.client("s3")
        paginator = client.get_paginator("list_objects_v2")

        notifiers = override_notifiers or self._notifiers

        for notifier in notifiers:
            log.debug(
                "Found bucket notification configuration: %r",
                notifier.configuration_id,
            )

        with contextlib.ExitStack() as stack:
            for notifier in notifiers:
                stack.enter_context(notifier)

            log.info(
                "Preparing to send notifications to %s destinations",
                len(notifiers),
            )
            for response in paginator.paginate(
                Bucket=self.bucket,
                Prefix=prefix,
            ):
                response_metadata = response["ResponseMetadata"]
                http_headers = response_metadata["HTTPHeaders"]

                filtered_entries = (
                    entry
                    for entry in response.get("Contents", ())
                    if not entry_filter or entry_filter.passes(entry)
                )
                for entry in filtered_entries:
                    log.info(
                        "%s %s %s",
                        entry["LastModified"],
                        entry["Size"],
                        entry["Key"],
                    )
                    for notifier in notifiers:
                        notifier.batched_notify(
                            event_name=event_name,
                            record_template=self.get_record_template(
                                event_name=event_name,
                                http_headers=http_headers,
                            ),
                            entry=entry,
                        )

    def get_record_template(self, event_name: str, http_headers: dict) -> dict:
        # Message structure including field order from:
        # https://docs.aws.amazon.com/AmazonS3/latest/userguide/notification-content-structure.html
        return {
            "Records": [
                {
                    "eventVersion": "2.2",
                    "eventSource": "aws:s3",
                    "awsRegion": http_headers.get("x-amz-bucket-region"),
                    "eventTime": datetime.now(tz=timezone.utc).strftime(
                        "%Y-%m-%dT%H:%M:%S.%fZ",
                    ),
                    "eventName": event_name,
                    "userIdentity": {
                        "principalId": self._user_identity,
                    },
                    "requestParameters": {
                        "sourceIPAddress": "0.0.0.0",
                    },
                    "responseElements": {
                        "x-amz-request-id": http_headers.get("x-amz-request-id"),
                        "x-amz-id-2": http_headers.get("x-amz-id-2"),
                    },
                    "s3": {
                        "s3SchemaVersion": "1.0",
                        "configurationId": FormatValue("configuration_id"),
                        "bucket": {
                            "name": self.bucket,
                            "ownerIdentity": {
                                # TODO(reweeden): Get this value somehow?
                                # get_bucket_acl can get you DisplayName but
                                # not PrincipalId.
                                "principalId": None,
                            },
                            "arn": f"arn:aws:s3:::{self.bucket}",
                        },
                        "object": {
                            "key": FormatValue('entry["Key"]'),
                            "size": FormatValue('entry["Size"]'),
                            "eTag": FormatValue('entry["ETag"]'),
                            "versionId": FormatValue('entry.get("VersionId")'),
                            # Sequencers seem to be globally valid with no
                            # documented expiration time. Therefore, in order to
                            # send useful values we'd have to know the current
                            # sequencer value for an object. However, therefore
                            # any fake value we send here would be wrong anyway
                            # so we just send a null to signal that this is a
                            # fake notification.
                            "sequencer": None,
                        },
                    },
                },
            ],
        }
