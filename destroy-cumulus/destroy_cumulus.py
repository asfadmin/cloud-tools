import argparse
import contextlib
import functools
import itertools
import json
import logging
import re
import sys
import time
from collections import defaultdict
from importlib.metadata import Distribution
from platform import python_version
from typing import Protocol

import boto3
import botocore

log = logging.getLogger(__name__)


HELP = """
This script searches AWS resources which are known to be created by cumulus
and tears down the ones with a matching prefix. This should only be used as a
tool to aid in finding orphaned resources that were not cleaned up by
terraform, and not as a replacement for terraform itself.

The script has two stages:

1. Resource gathering

    In this stage, the script queries a number of AWS services and compiles
    any that have a matching prefix into a list. After all services have been
    queried, the full list of matching resources is displayed.

2. Resource teardown

    After confirming the prompt, all resources will be destroyed one by one.
    There are some cases where a resource could fail to destroy and the script
    will need to be run again. For example, security groups are notorious for
    failing to destroy due to in-use network interfaces, which take a while to
    become unattached after their lambda function or EC2 instance is destroyed.

# Examples

To destroy all tagged and prefixed resources with the prefix `some-prefix`:

  destroy_cumulus.py some-prefix

To destroy all tagged and prefixed resources with the prefix `some-prefix`
except for resources with the prefix `some-prefix-ok1` or `some-prefix-ok2`:

  destroy_cumulus.py some-prefix --exclude some-prefix-ok1 some-prefix-ok2

To destroy all tagged and prefixed DynamoDB tables and RDS clusters with the
prefix `some-prefix` and printing verbose output:

  destroy_cumulus.py -v some-prefix --filter dynamodb:table rds:cluster
"""

# Developer notes
#
# Resource gathering is implemented through 'collector' objects. A collector is
# defined through the `Collector` protocol type.
# Most "Resource's" are currently implemented as collectors that know how to
# find that type of resource. These type of collectors should always be finding
# resources by name prefix, as there is already a TaggedResourceCollector that
# can find resources by 'Deployment' tag.
#
# Resource teardown is implemented as the `delete(get_client)` method on
# 'Resource' objects. To add support for a new type of resource, just implement
# a subclass of `Resource`. The only method that is required to implement is
# `delete`, however, it is generally also a good idea to implement `gather`
# and to add the resource to the RESOURCE_DESTRUCTION_ORDER list of the main
# manager object.
#
# Resource classes are defined in this file in alphabetical order.


class Arn:
    def __init__(self, arn):
        self._arn = arn

        _arn, self.partition, self.service, self.region, self.account, ident = arn.split(":", 5)
        colon_idx = ident.find(":")
        slash_idx = ident.find("/")

        if colon_idx == -1 and slash_idx == -1:
            # No colons or slashes
            self.type = ""
            self.id = ident
            self.name = self.id
            self.type_id = self.service
            return
        elif colon_idx == -1:
            # Only slashes
            self.type, *rest = ident.split("/", 1)
            rest = "".join(rest)
            if self.service == "apigateway":
                # Weird special case for apigateway where arns look like this:
                # arn:aws:apigateway:us-west-2::/restapis/d36my9ab58
                # For nested resources like Stages, Methods etc the id portion
                # follows the pattern:
                # ::/restapis/<api-id>/<subtype>/<subtype-id>/<sub-subtype>/<sub-subtype-id>/...
                rest_parts = rest.split("/")
                self.type = "-".join(rest_parts[::2])
                self.name = "/".join(rest_parts[1::2])
                self.id = self.name
            elif self.service == "iam":
                # Special case for roles where the role names can be prefixed such as
                # arn:aws:iam::123456789012:role/ngap/system/s3-all-region-access-role
                self.id = rest
                self.name = rest.split("/")[-1]
            else:
                self.name, *rest = rest.split("/", 1)
                self.id = "".join(rest)
            if not self.id:
                self.id = self.name
            self.type_id = f"{self.service}:{self.type}"
        elif slash_idx == -1 or colon_idx < slash_idx:
            # Only colons or colons come first
            self.type, self.id = ident.split(":", 1)
            if ":" in self.id:
                self.name, self.id = self.id.split(":", 1)
            else:
                self.name = self.id
            self.type_id = f"{self.service}:{self.type}"
        else:
            # Slashes come first
            self.type, ident = ident.split("/", 1)
            self.name, self.id = ident.rsplit(":", 1)
            self.type_id = f"{self.service}:{self.type}"

    def __str__(self):
        return self._arn


class Collector(Protocol):
    @classmethod
    def gather(cls, get_client, name_matcher, options) -> list["Resource"]:
        pass


class Resource:
    TYPE_FILTER = object()
    TYPES = {}

    def __init_subclass__(cls, register=True, **kwargs):
        if register:
            if cls.TYPE_FILTER is Resource.TYPE_FILTER:
                raise RuntimeError(f"'{cls.__name__}' missing 'TYPE_FILTER'")

            Resource.TYPES[cls.TYPE_FILTER] = cls

        super().__init_subclass__(**kwargs)

    def __init__(self, name, id, *, arn=None, tags=()):
        self.name = name
        self.id = id
        self.arn = arn
        self.tags = _tag_dict(tags)

    @classmethod
    def from_arn(cls, arn, *, tags=()):
        return cls(arn.name, arn.id, arn=arn, tags=tags)

    def load(self, get_client):
        """Load additional data necessary to destroy the resource. This will be
        called immediately after `gather` and before `delete`.
        """
        pass

    @classmethod
    def load_bulk(cls, get_client, resources):
        """Bulk version of `load` for optimizing API calls when data can be
        returned in bulk. The default implementation simply calls `load` on
        each resource.
        """
        for resource in resources:
            resource.load(get_client)

    def delete(self, get_client):
        """Destroy this resource"""
        raise NotImplementedError(
            f"Method 'delete' is not implemented for {self.__class__.__name__}",
        )

    def get_dependencies(self):
        """Return a list of resources which should be displayed as children of
        this resource, and need to be destroyed before this resource can be
        destroyed.

        Generally, resources returned as dependencies of another resource
        should not be gathered at the top level.
        """
        return []

    def __str__(self):
        return " ".join(line.strip() for line in self.display(include_tags=False))

    def get_display_name(self):
        return self.name

    def display(self, include_tags=True):
        deployment = self.tags.get("Deployment")
        if deployment is not None:
            deployment = f" ({deployment}) "

        name = self.get_display_name()
        header_line = f"[{self.__class__.__name__}]{deployment or ' '}{name}"

        if include_tags:
            tags = self.tags.copy()
            tags.pop("Deployment", None)

            if tags:
                tags_list = [f"  {k}={v}" for k, v in tags.items()]
                return [header_line, *tags_list]

        return [header_line]

    def get_sort_key(self):
        return self.get_display_name()

    # These implementations are for de-duplicating using a set()
    # Some aws api calls don't return much information so we may not always
    # have access to the entire ARN
    def __hash__(self):
        return hash((self.__class__, self.id))

    def __eq__(self, other):
        return (self.__class__, self.id) == (other.__class__, other.id)

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name={self.name!r}, id={self.id!r})"


class StateResource(Resource, register=False):
    """A resource with a state attribute"""

    def __init__(self, name, id, *, state=None, arn=None, tags=()):
        super().__init__(name, id, arn=arn, tags=tags)
        self.state = state

    @classmethod
    def from_arn(cls, arn, *, state=None, tags=()):
        return cls(arn.name, arn.id, state=state, arn=arn, tags=tags)

    def display(self, *args, **kwargs):
        lines = super().display(*args, **kwargs)
        if self.state:
            lines[0] = lines[0] + f" ({self.state})"
        return lines


class VersionedResource(Resource, register=False):
    """A resource where the arn ends with a ':<VersionNumber>'"""

    def get_display_name(self):
        return f"{self.name}:{self.id}"

    def get_sort_key(self):
        return (self.name, int(self.id))

    def __hash__(self):
        return hash((self.__class__, self.id))

    def __eq__(self, other):
        return (
            self.__class__,
            self.name,
            self.id,
        ) == (
            other.__class__,
            other.name,
            other.id,
        )


class TaggedResourceCollector:
    RDS_RID_PATTERN = re.compile("cluster-[a-zA-Z0-9]+")

    def __init__(self, type_filters=(), tag_filters=()):
        self.type_filters = type_filters
        self.tag_filters = tag_filters

    def gather(self, get_client, name_matcher, _options):
        client = get_client("resourcegroupstaggingapi")
        tag_paginator = client.get_paginator("get_tag_values")
        paginator = client.get_paginator("get_resources")

        tag_filters = self.tag_filters
        if not tag_filters:
            tag_values = [
                tag
                for response in tag_paginator.paginate(Key="Deployment")
                for tag in response["TagValues"]
                if name_matcher.matches(tag)
            ]

            if not tag_values:
                return []

            tag_filters = [dict(Key="Deployment", Values=tag_values)]

        entries = [
            entry
            for response in paginator.paginate(
                TagFilters=tag_filters,
                ResourceTypeFilters=self.type_filters,
            )
            for entry in response["ResourceTagMappingList"]
        ]

        resources = []
        for entry in entries:
            arn = Arn(entry["ResourceARN"])

            # Ignored ARNs
            if arn.type_id in (
                "apigateway:restapis-stages",
                "application-autoscaling:scalable-target",
                "ecs:service",
            ):
                log.debug(
                    "Skipping arn '%s' for type '%s' as it is a known child "
                    "of a different resource and will be destroyed "
                    "automatically when the parent is destroyed.",
                    arn,
                    arn.type_id,
                )
                continue

            cls = Resource.TYPES.get(arn.type_id)
            if cls is None:
                log.warning("Unhandled arn '%s' for type '%s'", arn, arn.type_id)
                continue

            # https://github.com/asfadmin/cloud-tools/issues/13
            #
            # The ResourceGroupsTaggingAPI seems to return the same RDS cluster
            # twice with two different ARNs. Once using the DBClusterIdentifier
            # and once using the DbClusterResourceId. Here we look for the arn
            # matching the DbClusterResourceId format and ignore it.
            if arn.type_id == "rds:cluster" and self.RDS_RID_PATTERN.match(arn.id):
                continue

            resources.append(
                cls.from_arn(
                    arn,
                    tags=entry.get("Tags", ()),
                ),
            )

        return resources


class UnnamedIAMRoleCollector:
    """Collect IAM roles named `terraform*` by looking at the roles policies
    and checking the policy resources against the stack prefix.
    """

    def __init__(self, type_filters=()):
        self.type_filters = type_filters

    def gather(self, get_client, name_matcher, _options):
        if self.type_filters and "iam:role" not in self.type_filters:
            return []

        client = get_client("iam")
        role_paginator = client.get_paginator("list_roles")
        attached_policy_paginator = client.get_paginator("list_attached_role_policies")
        inline_policy_paginator = client.get_paginator("list_role_policies")

        return [
            IAMRole(
                role_name,
                entry["RoleId"],
                arn=Arn(entry["Arn"]),
                tags=entry.get("Tags", ()),
            )
            for response in role_paginator.paginate()
            for entry in response.get("Roles", ())
            if (
                (role_name := entry["RoleName"]).startswith("terraform")
                and (
                    self._has_matching_attached_policy(
                        client,
                        attached_policy_paginator.paginate(RoleName=role_name),
                        name_matcher,
                    )
                    or self._has_matching_inline_policy(
                        client,
                        inline_policy_paginator.paginate(RoleName=role_name),
                        role_name,
                        name_matcher,
                    )
                )
            )
        ]

    def _has_matching_attached_policy(self, client, attached_policies, name_matcher):
        for response in attached_policies:
            for entry in response.get("AttachedPolicies", ()):
                policy_arn = entry["PolicyArn"]

                response = client.get_policy(PolicyArn=policy_arn)
                version_id = response["Policy"]["DefaultVersionId"]

                response = client.get_policy_version(
                    PolicyArn=policy_arn,
                    VersionId=version_id,
                )
                document = response["Document"]
                if isinstance(document, str):
                    document = json.loads(document)

                if self._policy_document_matches(document, name_matcher):
                    return True

        return False

    def _has_matching_inline_policy(self, client, inline_policies, role_name, name_matcher):
        for response in inline_policies:
            for policy_name in response.get("PolicyNames", ()):
                response = client.get_role_policy(
                    RoleName=role_name,
                    PolicyName=policy_name,
                )
                document = response["PolicyDocument"]
                if isinstance(document, str):
                    document = json.loads(document)

                if self._policy_document_matches(document, name_matcher):
                    return True

        return False

    def _policy_document_matches(self, document, name_matcher):
        version = document["Version"]
        if version != "2012-10-17":
            log.warning("Unsupported IAM document with version '%s'", version)

        for statement in document.get("Statement", ()):
            resources = statement.get("Resource", ())
            if isinstance(resources, str):
                resources = [resources]

            for resource in resources:
                if resource == "*":
                    continue

                arn = Arn(resource)
                if arn.name != "*" and name_matcher.matches(arn.name):
                    return True

                # ARN parsing for bucket objects is a little weird
                if arn.type_id.startswith("s3:"):
                    if arn.type != "*" and name_matcher.matches(arn.type):
                        return True

        return False


#
# Resource subclasses defined in alphabetical order
#


class Activity(Resource):
    TYPE_FILTER = "states:activity"

    @classmethod
    def gather(cls, get_client, name_matcher, _options):
        client = get_client("stepfunctions")
        paginator = client.get_paginator("list_activities")

        return [
            cls.from_arn(
                Arn(entry["activityArn"]),
            )
            for response in paginator.paginate()
            for entry in response.get("activities", ())
            if name_matcher.matches(entry["name"])
        ]

    def delete(self, get_client):
        client = get_client("stepfunctions")
        client.delete_activity(activityArn=str(self.arn))


class ApiGateway(Resource):
    TYPE_FILTER = "apigateway:restapis"

    @classmethod
    def gather(cls, get_client, name_matcher, _options):
        client = get_client("apigateway")
        paginator = client.get_paginator("get_rest_apis")

        return [
            cls(
                name,
                entry["id"],
                tags=[
                    # ruff hint
                    dict(Key=k, Value=v)
                    for k, v in entry.get("tags", {}).items()
                ],
            )
            for response in paginator.paginate()
            for entry in response.get("items", ())
            if name_matcher.matches(name := entry["name"])
        ]

    def delete(self, get_client):
        client = get_client("apigateway")
        client.delete_rest_api(restApiId=self.id)

    def display(self, *args, **kwargs):
        lines = super().display(*args, **kwargs)
        if self.name != self.id:
            lines[0] = "/".join((lines[0], self.id))

        return lines


class AthenaWorkGroup(Resource):
    TYPE_FILTER = "athena:workgroup"

    @classmethod
    def gather(cls, get_client, name_matcher, _options):
        # For some reason cumulus decided to change the naming convention for
        # these resources.
        name_matcher = name_matcher.replace("-", "_")

        client = get_client("athena")
        response = client.list_work_groups()

        return [
            # ruff hint
            cls(name, name)
            for entry in response.get("WorkGroups", ())
            if name_matcher.matches(name := entry["Name"])
        ]

    def delete(self, get_client):
        client = get_client("athena")
        client.delete_work_group(
            WorkGroup=self.name,
            RecursiveDeleteOption=True,
        )


class Bucket(Resource):
    TYPE_FILTER = "s3"

    @classmethod
    def gather(cls, get_client, name_matcher, _options):
        client = get_client("s3")
        response = client.list_buckets()

        return [
            # ruff hint
            cls(name, name)
            for entry in response.get("Buckets", ())
            if name_matcher.matches(name := entry["Name"])
        ]

    def delete(self, get_client):
        client = get_client("s3")
        version_paginator = client.get_paginator("list_object_versions")

        def list_objects():
            for response in version_paginator.paginate(Bucket=self.name):
                yield from (
                    {
                        "Key": entry["Key"],
                        "VersionId": entry["VersionId"],
                    }
                    for entry in response.get("Versions", ())
                )
                yield from (
                    {
                        "Key": entry["Key"],
                        "VersionId": entry["VersionId"],
                    }
                    for entry in response.get("DeleteMarkers", ())
                )

        for object_batch in _batched(list_objects(), 1000):
            client.delete_objects(
                Bucket=self.name,
                Delete={"Objects": object_batch},
            )

        client.delete_bucket(Bucket=self.name)


class CloudFormationStack(Resource):
    TYPE_FILTER = "cloudformation:stack"

    @classmethod
    def gather(cls, get_client, name_matcher, _options):
        client = get_client("cloudformation")
        paginator = client.get_paginator("list_stacks")

        return [
            cls.from_arn(Arn(entry["StackId"]))
            for response in paginator.paginate()
            for entry in response.get("StackSummaries", ())
            if name_matcher.matches(entry["StackName"])
            if entry["StackStatus"] not in ("DELETE_IN_PROGRESS", "DELETE_COMPLETE")
        ]

    def delete(self, get_client):
        client = get_client("cloudformation")
        client.delete_stack(StackName=self.name)


class CloudWatchAlarm(Resource):
    TYPE_FILTER = "cloudwatch:alarm"

    @classmethod
    def gather(cls, get_client, name_matcher, _options):
        client = get_client("cloudwatch")
        paginator = client.get_paginator("describe_alarms")

        kwargs = (
            dict(
                AlarmNamePrefix=name_matcher.prefix,
            )
            if name_matcher.prefix
            else {}
        )

        return [
            cls.from_arn(Arn(entry["AlarmArn"]))
            for response in paginator.paginate(**kwargs)
            # NOTE: Ignoring composite alarms here
            for entry in response.get("MetricAlarms", ())
            if name_matcher.matches(entry["AlarmName"])
        ]

    def delete(self, get_client):
        client = get_client("cloudwatch")
        # NOTE: Could actually do a bulk delete here
        client.delete_alarms(AlarmNames=[self.name])


class CloudWatchDashboard(Resource):
    """These are expensive: $"""

    TYPE_FILTER = "cloudwatch:dashboard"

    @classmethod
    def gather(cls, get_client, name_matcher, _options):
        client = get_client("cloudwatch")
        paginator = client.get_paginator("list_dashboards")

        kwargs = (
            dict(
                DashboardNamePrefix=name_matcher.prefix,
            )
            if name_matcher.prefix
            else {}
        )

        return [
            cls.from_arn(Arn(entry["DashboardArn"]))
            for response in paginator.paginate(**kwargs)
            for entry in response.get("DashboardEntries", ())
            if name_matcher.matches(entry["DashboardName"])
        ]

    def delete(self, get_client):
        client = get_client("cloudwatch")
        # NOTE: Could actually do a bulk delete here
        client.delete_dashboards(DashboardNames=[self.name])


class CloudWatchEventRule(Resource):
    TYPE_FILTER = "events:rule"

    @classmethod
    def gather(cls, get_client, name_matcher, _options):
        client = get_client("events")
        rule_paginator = client.get_paginator("list_rules")
        target_paginator = client.get_paginator("list_targets_by_rule")

        kwargs = (
            dict(
                NamePrefix=name_matcher.prefix,
            )
            if name_matcher.prefix
            else {}
        )

        named_rules = [
            cls.from_arn(Arn(entry["Arn"]))
            for response in rule_paginator.paginate(**kwargs)
            for entry in response.get("Rules", ())
            if name_matcher.matches(entry["Name"])
        ]

        if name_matcher.matches("terraform"):
            return named_rules

        # Some rules don't have names set and so they default to 'terraform*'
        # NOTE: These subqueries can be quite slow if there are a lot of
        # rules named 'terraform*'
        unnamed_rules = [
            cls.from_arn(Arn(entry["Arn"]))
            for response in rule_paginator.paginate(NamePrefix="terraform")
            for entry in response.get("Rules", ())
            if any(
                name_matcher.matches(Arn(entry["Arn"]).name)
                for response in target_paginator.paginate(Rule=entry["Name"])
                for entry in response.get("Targets", ())
            )
        ]
        return [*named_rules, *unnamed_rules]

    def delete(self, get_client):
        client = get_client("events")
        paginator = client.get_paginator("list_targets_by_rule")

        target_ids = [
            # ruff hint
            entry["Id"]
            for response in paginator.paginate(Rule=self.name)
            for entry in response["Targets"]
        ]

        if target_ids:
            client.remove_targets(
                Rule=self.name,
                Ids=target_ids,
            )

        client.delete_rule(Name=self.name)


class CloudWatchLogGroup(Resource):
    TYPE_FILTER = "logs:log-group"

    @classmethod
    def gather(cls, get_client, name_matcher, _options):
        client = get_client("logs")
        paginator = client.get_paginator("describe_log_groups")

        kwargs = (
            dict(
                logGroupNamePattern=name_matcher.prefix,
            )
            if name_matcher.prefix
            else {}
        )

        return [
            # For some reason the arn here takes the form of a 'log-stream'
            # with the stream name set to '*'. This causes the arn id parsing
            # to think all log groups have the same id of '*'.
            # Note. This could also be fixed by reworking the ARN parsing to
            # have specific knowledge about each service's ARN format.
            cls.from_arn(Arn(entry["arn"][:-2]))
            for response in paginator.paginate(**kwargs)
            for entry in response.get("logGroups", ())
            if any(
                # ruff hint
                section and name_matcher.matches(section)
                for section in entry["logGroupName"].split("/")
            )
        ]

    def delete(self, get_client):
        client = get_client("logs")
        client.delete_log_group(logGroupName=self.name)


class DynamoDBTable(Resource):
    TYPE_FILTER = "dynamodb:table"

    @classmethod
    def gather(cls, get_client, name_matcher, _options):
        client = get_client("dynamodb")
        paginator = client.get_paginator("list_tables")

        return [
            cls(name, name)
            for response in paginator.paginate()
            for name in response.get("TableNames", ())
            if name_matcher.matches(name)
        ]

    def delete(self, get_client):
        client = get_client("dynamodb")
        client.delete_table(TableName=self.name)


class ECRRepository(Resource):
    """Possible workflow resource. Not part of core."""

    TYPE_FILTER = "ecr:repository"

    @classmethod
    def gather(cls, get_client, name_matcher, _options):
        client = get_client("ecr")
        paginator = client.get_paginator("describe_repositories")

        return [
            cls(name, name)
            for response in paginator.paginate()
            for entry in response.get("repositories", ())
            if name_matcher.matches(name := entry["repositoryName"])
        ]

    def delete(self, get_client):
        client = get_client("ecr")
        client.delete_repository(
            repositoryName=self.name,
            force=True,
        )


class ECSCluster(StateResource):
    TYPE_FILTER = "ecs:cluster"

    def __init__(self, name, id, *, services=(), state=None, arn=None, tags=()):
        super().__init__(name, id, state=state, arn=arn, tags=tags)
        self.services = sorted(
            services,
            key=lambda res: (res.name, res.id),
        )

    @classmethod
    def gather(cls, get_client, name_matcher, _options):
        client = get_client("ecs")
        paginator = client.get_paginator("list_clusters")
        services_paginator = client.get_paginator("list_services")

        return [
            cls(
                name=arn.name,
                id=arn.id,
                services=[
                    ECSService.from_arn(Arn(service_arn_))
                    for response in services_paginator.paginate(
                        cluster=arn_,
                    )
                    for service_arn_ in response["serviceArns"]
                ],
                arn=arn,
            )
            for response in paginator.paginate()
            for arn_ in response["clusterArns"]
            if name_matcher.matches((arn := Arn(arn_)).name)
        ]

    def delete(self, get_client):
        client = get_client("ecs")
        client.delete_cluster(cluster=self.name)

    def get_dependencies(self):
        return self.services


class ECSService(Resource):
    TYPE_FILTER = "ecs:service"

    def __init__(self, name, id, cluster, *, arn=None, tags=()):
        super().__init__(name, id, arn=arn, tags=tags)
        self.cluster = cluster

    @classmethod
    def from_arn(cls, arn, *, tags=()):
        # TODO(reweeden): The Arn parsing isn't quite right
        cluster = arn.name
        service = arn.id
        return cls(service, service, cluster, arn=arn, tags=tags)

    def delete(self, get_client):
        client = get_client("ecs")
        client.update_service(
            cluster=self.cluster,
            service=self.name,
            desiredCount=0,
        )
        client.delete_service(
            cluster=self.cluster,
            service=self.name,
        )


class ECSTaskDefinition(StateResource, VersionedResource):
    TYPE_FILTER = "ecs:task-definition"

    @classmethod
    def gather(cls, get_client, name_matcher, _options):
        client = get_client("ecs")
        paginator = client.get_paginator("list_task_definitions")

        return [
            cls(arn.name, arn.id, state=status, arn=arn)
            for status in ("ACTIVE", "INACTIVE", "DELETE_IN_PROGRESS")
            for response in paginator.paginate(status=status)
            for arn_ in response["taskDefinitionArns"]
            if name_matcher.matches((arn := Arn(arn_)).name)
        ]

    def delete(self, get_client):
        client = get_client("ecs")
        if self.state != "DELETE_IN_PROGRESS":
            client.deregister_task_definition(taskDefinition=str(self.arn))
        # NOTE: Could actually do a bulk delete here
        client.delete_task_definitions(taskDefinitions=[str(self.arn)])



class ElasticsearchDomain(Resource):
    """These are expensive: $$"""

    TYPE_FILTER = "es:domain"

    @classmethod
    def gather(cls, get_client, name_matcher, _options):
        client = get_client("opensearch")

        return [
            cls(name, name)
            for entry in client.list_domain_names()["DomainNames"]
            if name_matcher.matches(name := entry["DomainName"])
        ]

    def delete(self, get_client):
        client = get_client("opensearch")
        client.delete_domain(DomainName=self.name)


class EventSourceMapping(Resource):
    TYPE_FILTER = "lambda:event-source-mapping"

    def __init__(
        self,
        id,
        *,
        arn=None,
        tags=(),
        event_source_arn=None,
        function_arn=None,
    ):
        super().__init__(id, id, arn=arn, tags=tags)
        self.event_source_arn = event_source_arn
        self.function_arn = function_arn

    @classmethod
    def from_arn(cls, arn, *, tags=()):
        return cls(arn.id, arn=arn, tags=tags)

    @classmethod
    def gather(cls, get_client, name_matcher, options):
        client = get_client("lambda")
        paginator = client.get_paginator("list_event_source_mappings")

        # For large numbers of event source mappings, we see the following error
        # An error occurred (ServiceException) when calling the
        # ListEventSourceMappings operation (reached max retries: 4): An error
        # occurred and the request cannot be processed.
        #
        # Setting `MaxItems` is able to mitigate this error, but of course it
        # limits how many event source mappings will actually be scanned.
        kwargs = (
            dict(
                PaginationConfig={"MaxItems": options["MaxItems"]},
            )
            if "MaxItems" in options
            else {}
        )

        return [
            cls(
                entry["UUID"],
                arn=Arn(entry["EventSourceMappingArn"]),
                event_source_arn=Arn(entry["EventSourceArn"]),
                function_arn=function_arn,
            )
            for response in paginator.paginate(**kwargs)
            for entry in response.get("EventSourceMappings", ())
            if name_matcher.matches((function_arn := Arn(entry["FunctionArn"])).name)
        ]

    def load(self, get_client):
        if self.event_source_arn and self.function_arn:
            return

        client = get_client("lambda")
        response = client.get_event_source_mapping(UUID=self.id)

        self.event_source_arn = Arn(response["EventSourceArn"])
        self.function_arn = Arn(response["FunctionArn"])

    def delete(self, get_client):
        client = get_client("lambda")
        client.delete_event_source_mapping(UUID=self.id)

    def get_display_name(self):
        if not self.function_arn and not self.event_source_arn:
            return self.id

        event_source_name = self.event_source_arn.name if self.event_source_arn else "????"
        function_name = self.function_arn.name if self.function_arn else "????"

        return f"{event_source_name} -> {function_name}"


class GlueDatabase(Resource):
    TYPE_FILTER = "glue:database"

    def __init__(self, name, catalog_id, *, arn=None, tags=()):
        super().__init__(name, name, arn=arn, tags=tags)
        self.catalog_id = catalog_id

    @classmethod
    def gather(cls, get_client, name_matcher, _options):
        # For some reason cumulus decided to change the naming convention for
        # these resources.
        name_matcher = name_matcher.replace("-", "_")

        client = get_client("glue")
        paginator = client.get_paginator("get_databases")

        return [
            cls(name, entry["CatalogId"])
            for response in paginator.paginate()
            for entry in response.get("DatabaseList", ())
            if name_matcher.matches(name := entry["Name"])
        ]

    def delete(self, get_client):
        client = get_client("glue")
        client.delete_database(CatalogId=self.catalog_id, Name=self.name)


class IAMInstanceProfile(Resource):
    TYPE_FILTER = "iam:instanceprofile"

    def __init__(self, name, id, *, roles=(), arn=None, tags=()):
        super().__init__(name, id, arn=arn, tags=tags)
        self.roles = roles

    @classmethod
    def from_arn(cls, arn, *, roles=(), tags=()):
        return cls(arn.name, arn.id, roles=roles, arn=arn, tags=tags)

    @classmethod
    def gather(cls, get_client, name_matcher, _options):
        client = get_client("iam")
        paginator = client.get_paginator("list_instance_profiles")

        return [
            cls.from_arn(
                Arn(entry["Arn"]),
                roles=[role["RoleName"] for role in entry["Roles"]],
                tags=entry.get("Tags", ()),
            )
            for response in paginator.paginate()
            for entry in response.get("InstanceProfiles", ())
            if name_matcher.matches(entry["InstanceProfileName"])
        ]

    def delete(self, get_client):
        client = get_client("iam")

        for role in self.roles:
            client.remove_role_from_instance_profile(
                InstanceProfileName=self.name,
                RoleName=role,
            )

        client.delete_instance_profile(InstanceProfileName=self.name)


class IAMPolicy(Resource):
    TYPE_FILTER = "iam:policy"

    @classmethod
    def gather(cls, get_client, name_matcher, _options):
        client = get_client("iam")
        paginator = client.get_paginator("list_policies")

        return [
            cls(
                name,
                entry["PolicyId"],
                arn=Arn(entry["Arn"]),
                tags=entry.get("Tags", ()),
            )
            for response in paginator.paginate(Scope="Local")
            for entry in response.get("Policies", ())
            if name_matcher.matches(name := entry["PolicyName"])
        ]

    def delete(self, get_client):
        client = get_client("iam")
        paginator = client.get_paginator("list_policy_versions")

        for response in paginator.paginate(PolicyArn=str(self.arn)):
            for entry in response["Versions"]:
                if entry["IsDefaultVersion"]:
                    # Not allowed to delete default version
                    continue

                client.delete_policy_version(
                    PolicyArn=str(self.arn),
                    VersionId=entry["VersionId"],
                )

        client.delete_policy(PolicyArn=str(self.arn))

    def get_display_name(self):
        if self.arn:
            return self.arn.id

        return self.name


class IAMRole(Resource):
    TYPE_FILTER = "iam:role"

    @classmethod
    def gather(cls, get_client, name_matcher, _options):
        client = get_client("iam")
        paginator = client.get_paginator("list_roles")

        return [
            cls(
                name,
                entry["RoleId"],
                arn=Arn(entry["Arn"]),
                tags=entry.get("Tags", ()),
            )
            for response in paginator.paginate()
            for entry in response.get("Roles", ())
            if name_matcher.matches(name := entry["RoleName"])
        ]

    def delete(self, get_client):
        client = get_client("iam")
        attached_policy_paginator = client.get_paginator("list_attached_role_policies")
        inline_policy_paginator = client.get_paginator("list_role_policies")

        for response in attached_policy_paginator.paginate(RoleName=self.name):
            for entry in response["AttachedPolicies"]:
                client.detach_role_policy(
                    RoleName=self.name,
                    PolicyArn=entry["PolicyArn"],
                )

        for response in inline_policy_paginator.paginate(RoleName=self.name):
            for policy in response["PolicyNames"]:
                client.delete_role_policy(
                    RoleName=self.name,
                    PolicyName=policy,
                )

        client.delete_role(RoleName=self.name)

    def get_display_name(self):
        if self.arn:
            return self.arn.id

        return self.name


class KMSKey(Resource):
    TYPE_FILTER = "kms:key"

    # We need to fetch these through the ResourceGroupsTaggingAPI since their
    # names are just random UUIDs and don't contain the deploy name

    def delete(self, get_client):
        client = get_client("kms")
        client.schedule_key_deletion(KeyId=self.name)


class LambdaFunction(Resource):
    TYPE_FILTER = "lambda:function"

    @classmethod
    def gather(cls, get_client, name_matcher, _options):
        client = get_client("lambda")
        paginator = client.get_paginator("list_functions")

        return [
            cls.from_arn(Arn(entry["FunctionArn"]))
            for response in paginator.paginate()
            for entry in response.get("Functions", ())
            if name_matcher.matches(entry["FunctionName"])
        ]

    def delete(self, get_client):
        client = get_client("lambda")
        client.delete_function(FunctionName=str(self.arn))


class LambdaLayerVersion(VersionedResource):
    TYPE_FILTER = "lambda:layer"

    @classmethod
    def gather(cls, get_client, name_matcher, _options):
        client = get_client("lambda")
        layer_paginator = client.get_paginator("list_layers")
        version_paginator = client.get_paginator("list_layer_versions")

        return [
            cls.from_arn(Arn(ventry["LayerVersionArn"]))
            for response in layer_paginator.paginate()
            for entry in response.get("Layers", ())
            if name_matcher.matches(name := entry["LayerName"])
            for vresponse in version_paginator.paginate(LayerName=name)
            for ventry in vresponse["LayerVersions"]
        ]

    def delete(self, get_client):
        client = get_client("lambda")
        client.delete_layer_version(
            LayerName=self.name,
            VersionNumber=int(self.id),
        )


class NetworkInterface(StateResource):
    TYPE_FILTER = "ec2:network-interface"

    def delete(self, get_client):
        client = get_client("ec2")
        client.delete_network_interface(NetworkInterfaceId=self.id)

    def get_display_name(self):
        return self.name or self.id


class RDSCluster(Resource):
    TYPE_FILTER = "rds:cluster"

    @classmethod
    def gather(cls, get_client, name_matcher, _options):
        client = get_client("rds")
        paginator = client.get_paginator("describe_db_clusters")

        return [
            cls.from_arn(Arn(entry["DBClusterArn"]), tags=entry.get("TagList", ()))
            for response in paginator.paginate()
            for entry in response.get("DBClusters", ())
            if name_matcher.matches(entry["DBClusterIdentifier"])
        ]

    def delete(self, get_client):
        client = get_client("rds")
        client.delete_db_cluster(DBClusterIdentifier=self.id, SkipFinalSnapshot=True)


class RDSClusterParameterGroup(Resource):
    TYPE_FILTER = "rds:cluster-pg"

    @classmethod
    def gather(cls, get_client, name_matcher, _options):
        client = get_client("rds")
        paginator = client.get_paginator("describe_db_cluster_parameter_groups")

        return [
            cls.from_arn(Arn(entry["DBClusterParameterGroupArn"]))
            for response in paginator.paginate(
                # NOTE(08/30/24): Filters are not supported yet
            )
            for entry in response.get("DBClusterParameterGroups", ())
            if name_matcher.matches(entry["DBClusterParameterGroupName"])
        ]

    def delete(self, get_client):
        client = get_client("rds")
        client.delete_db_cluster_parameter_group(
            DBClusterParameterGroupName=self.name,
        )


class RDSSubnetGroup(Resource):
    TYPE_FILTER = "rds:subgrp"

    @classmethod
    def gather(cls, get_client, name_matcher, _options):
        client = get_client("rds")
        paginator = client.get_paginator("describe_db_subnet_groups")

        return [
            cls.from_arn(Arn(entry["DBSubnetGroupArn"]))
            for response in paginator.paginate(
                # NOTE(08/30/24): Filters are not supported yet
            )
            for entry in response.get("DBSubnetGroups", ())
            if name_matcher.matches(entry["DBSubnetGroupName"])
        ]

    def delete(self, get_client):
        client = get_client("rds")
        client.delete_db_subnet_group(DBSubnetGroupName=self.name)


class Secret(StateResource):
    TYPE_FILTER = "secretsmanager:secret"

    @classmethod
    def gather(cls, get_client, name_matcher, _options):
        client = get_client("secretsmanager")
        paginator = client.get_paginator("list_secrets")

        return [
            cls.from_arn(
                Arn(entry["ARN"]),
                state="DELETED" if "DeletedDate" in entry else None,
                tags=entry.get("Tags", ()),
            )
            for response in paginator.paginate(
                Filters=[
                    dict(
                        Key="name",
                        Values=[name_matcher.prefix],
                    ),
                ]
            )
            for entry in response.get("SecretList", ())
            if name_matcher.matches(entry["Name"])
        ]

    def delete(self, get_client):
        client = get_client("secretsmanager")
        client.delete_secret(SecretId=str(self.arn), RecoveryWindowInDays=7)


class SecurityGroup(Resource):
    TYPE_FILTER = "ec2:security-group"

    def __init__(self, name, id, network_interfaces, *, arn=None, tags=()):
        super().__init__(name, id, arn=arn, tags=tags)
        self.network_interfaces = sorted(
            network_interfaces,
            key=lambda res: (res.name, res.id),
        )

    @classmethod
    def from_arn(cls, arn, *, tags=()):
        return cls(arn.name, arn.id, [], arn=arn, tags=tags)

    @classmethod
    def gather(cls, get_client, name_matcher, _options):
        client = get_client("ec2")
        paginator = client.get_paginator("describe_security_groups")

        return [
            cls(
                entry["GroupName"],
                entry["GroupId"],
                network_interfaces=[],
                tags=entry.get("Tags", ()),
            )
            for response in paginator.paginate(
                Filters=[
                    dict(
                        Name="group-name",
                        Values=[name_matcher.prefix + "*"],
                    ),
                ],
            )
            for entry in response.get("SecurityGroups", ())
            if name_matcher.matches(entry["GroupName"])
        ]

    def load(self, get_client):
        self.load_bulk(get_client, [self])

    @classmethod
    def load_bulk(cls, get_client, resources):
        client = get_client("ec2")
        paginator = client.get_paginator("describe_security_groups")
        eni_paginator = client.get_paginator("describe_network_interfaces")

        security_groups_by_id = {resource.id: resource for resource in resources}
        security_group_ids = list(security_groups_by_id.keys())

        for response in paginator.paginate(GroupIds=security_group_ids):
            for entry in response.get("SecurityGroups", ()):
                security_group = security_groups_by_id[entry["GroupId"]]

                security_group.name = entry["GroupName"]
                security_group.tags = _tag_dict(entry.get("Tags", ()))

        for response in eni_paginator.paginate(
            Filters=[
                dict(Name="group-id", Values=security_group_ids),
            ],
        ):
            for entry in response.get("NetworkInterfaces", ()):
                network_interface = NetworkInterface(
                    entry["Description"],
                    entry["NetworkInterfaceId"],
                    state=entry["Status"],
                    tags=entry.get("TagSet", ()),
                )
                for group_entry in entry["Groups"]:
                    security_group = security_groups_by_id.get(
                        group_entry["GroupId"],
                    )
                    if not security_group:
                        continue

                    security_group.network_interfaces.append(network_interface)

        for security_group in resources:
            security_group.network_interfaces.sort(
                key=lambda res: (res.name, res.id),
            )

    def delete(self, get_client):
        client = get_client("ec2")
        client.delete_security_group(GroupId=self.id)

    def get_dependencies(self):
        return self.network_interfaces


class SNSSubscription(Resource):
    TYPE_FILTER = "sns:subscription"

    def __init__(
        self,
        name,
        id,
        *,
        topic_arn=None,
        protocol=None,
        endpoint=None,
        arn=None,
        tags=(),
    ):
        super().__init__(name, id, arn=arn, tags=tags)
        self.topic_arn = topic_arn
        self.protocol = protocol
        self.endpoint = endpoint

    @classmethod
    def from_arn(cls, arn, *, topic_arn=None, protocol=None, endpoint=None, tags=()):
        return cls(
            arn.name,
            arn.id,
            topic_arn=topic_arn,
            protocol=protocol,
            endpoint=endpoint,
            arn=arn,
            tags=tags,
        )

    @classmethod
    def gather(cls, get_client, name_matcher, _options):
        client = get_client("sns")
        paginator = client.get_paginator("list_subscriptions")

        return [
            cls.from_arn(
                Arn(subscription_arn),
                topic_arn=topic_arn,
                protocol=entry["Protocol"],
                endpoint=entry["Endpoint"],
            )
            for response in paginator.paginate()
            for entry in response.get("Subscriptions", ())
            if name_matcher.matches((topic_arn := Arn(entry["TopicArn"])).name)
            if (subscription_arn := entry["SubscriptionArn"]) != "PendingConfirmation"
        ]

    def delete(self, get_client):
        client = get_client("sns")
        client.unsubscribe(SubscriptionArn=str(self.arn))

    def get_display_name(self):
        endpoint = self.get_endpoint_name()
        topic_name = self.get_topic_name()
        return f"({self.protocol}) {endpoint} <- {topic_name}"

    def get_topic_name(self):
        if self.topic_arn:
            return self.topic_arn.name

    def get_endpoint_name(self):
        if self.protocol in ("application", "firehose", "lambda", "sqs"):
            with contextlib.suppress(Exception):
                return Arn(self.endpoint).name
        return self.endpoint


class SNSTopic(Resource):
    TYPE_FILTER = "sns"

    @classmethod
    def gather(cls, get_client, name_matcher, _options):
        client = get_client("sns")
        paginator = client.get_paginator("list_topics")

        return [
            cls.from_arn(arn)
            for response in paginator.paginate()
            for entry in response.get("Topics", ())
            if name_matcher.matches((arn := Arn(entry["TopicArn"])).name)
        ]

    def delete(self, get_client):
        client = get_client("sns")
        client.delete_topic(TopicArn=str(self.arn))


class SQSQueue(Resource):
    TYPE_FILTER = "sqs"

    URL_PATTERN = re.compile(r"https://.+/\d{12}/(.+)")

    @classmethod
    def gather(cls, get_client, name_matcher, _options):
        client = get_client("sqs")
        paginator = client.get_paginator("list_queues")

        kwargs = (
            dict(
                QueueNamePrefix=name_matcher.prefix,
            )
            if name_matcher.prefix
            else {}
        )

        return [
            cls(name, name)
            for response in paginator.paginate(**kwargs)
            for url in response.get("QueueUrls", ())
            if (m := cls.URL_PATTERN.match(url)) and name_matcher.matches(name := m.group(1))
        ]

    def delete(self, get_client):
        client = get_client("sqs")
        client.delete_queue(QueueUrl=self.name)


class SSMParameter(Resource):
    TYPE_FILTER = "ssm:parameter"

    @classmethod
    def gather(cls, get_client, name_matcher, _options):
        client = get_client("ssm")
        paginator = client.get_paginator("describe_parameters")

        return [
            cls.from_arn(Arn(entry["ARN"]))
            # No filtering by tags because these have not been tagged in
            # CIRRUS-core in the past.
            for response in paginator.paginate()
            for entry in response.get("Parameters", ())
            if name_matcher.matches(entry["Name"])
        ]

    def delete(self, get_client):
        client = get_client("ssm")
        client.delete_parameter(Name=self.name)


class StepFunction(Resource):
    TYPE_FILTER = "states:stateMachine"

    @classmethod
    def gather(cls, get_client, name_matcher, _options):
        client = get_client("stepfunctions")
        paginator = client.get_paginator("list_state_machines")

        return [
            cls.from_arn(arn)
            for response in paginator.paginate()
            for entry in response.get("stateMachines", ())
            if name_matcher.matches((arn := Arn(entry["stateMachineArn"])).name)
        ]

    def delete(self, get_client):
        client = get_client("stepfunctions")
        client.delete_state_machine(stateMachineArn=str(self.arn))


#
# End of resource subclasses
#


class ResourceSet:
    def __init__(self, iterable=()):
        self._resources = {}
        self._resources_by_class = defaultdict(set)
        for item in iterable:
            self.add(item)

    def add(self, resource):
        if resource in self._resources:
            log.debug(
                "Updating already found [%s] %s",
                resource.__class__.__name__,
                resource.name,
            )
            old = self._resources.pop(resource)
            self._resources_by_class[resource.__class__].discard(resource)
            resource.tags.update(old.tags)

        self._resources[resource] = resource
        self._resources_by_class[resource.__class__].add(resource)

    def iter_by_class(self):
        for key, values in self._resources_by_class.items():
            if values:
                yield (key, values)

    def __iter__(self):
        return iter(self._resources.values())

    def __len__(self):
        return len(self._resources)

    def __repr__(self):
        return f"{self.__class__.__name__}({list(self._resources.values())})"


class CumulusDestroyer:
    # Resources will be destroyed in the order they are defined here, so put
    # dependent resources towards the end. Resources not listed will be
    # destroyed last.
    RESOURCE_DESTRUCTION_ORDER = [
        CloudFormationStack,
        ApiGateway,
        LambdaFunction,
        LambdaLayerVersion,
        StepFunction,
        Activity,
        EventSourceMapping,
        CloudWatchDashboard,
        CloudWatchAlarm,
        CloudWatchEventRule,
        ElasticsearchDomain,
        SNSSubscription,
        SNSTopic,
        SQSQueue,
        DynamoDBTable,
        ECSCluster,
        ECSTaskDefinition,
        ECRRepository,
        RDSCluster,
        RDSClusterParameterGroup,
        RDSSubnetGroup,
        SecurityGroup,
        CloudWatchLogGroup,
        IAMInstanceProfile,
        IAMRole,
        IAMPolicy,
        Secret,
        Bucket,
        KMSKey,
    ]

    DEFAULT_EXTRA_COLLECTORS = [
        TaggedResourceCollector,
    ]

    _SORT_KEY = {cls: i for i, cls in enumerate(RESOURCE_DESTRUCTION_ORDER)}

    def __init__(
        self,
        profile,
        name_matcher,
        type_filters=(),
        type_filters_exclude=(),
        auto_confirm=False,
        display_tags=False,
        gather_options={},
    ):
        self.session = boto3.Session(profile_name=profile)
        self.name_matcher = name_matcher
        self.type_filters = type_filters
        self.type_filters_exclude = type_filters_exclude
        self.auto_confirm = auto_confirm
        self.display_tags = display_tags
        self.gather_options = gather_options

    @functools.lru_cache()
    def client(self, *args, **kwargs):
        return self.session.client(*args, **kwargs)

    def destroy(self, resources=None):
        if resources is None:
            resources = self.gather()

        resources = sorted(
            resources,
            key=lambda res: (
                self._SORT_KEY.get(res.__class__, len(self._SORT_KEY)),
                res.__class__.__name__,
                res.tags.get("Deployment", ""),
                res.get_sort_key(),
            ),
        )

        if not resources:
            log.info("No resources to destroy")
            return

        log.info("Resources to delete:")
        for resource in resources:
            self._log_resource(resource)

        prompter = Prompter(self.auto_confirm)

        prompt = f"Delete these {len(resources)} resources?"
        if not prompter.confirm_group(prompt, group=None):
            log.info("Destruction cancelled!")
            return

        total = len(resources)
        attempted, failures = 0, 0
        for resource in resources:
            prompt = f"Delete all {pluralize(resource.__class__.__name__)}?"
            group = resource.__class__.__name__
            if not prompter.confirm_group(prompt, group):
                continue

            if not prompter.confirm(f"Delete {resource}?", group):
                continue

            try:
                attempted += 1
                self._call_delete(resource)
            except botocore.exceptions.ClientError as e:
                log.warning("Failed to delete %s: %s", resource, e)
                failures += 1

        if failures != 0:
            log.warning("%d resources failed to delete!", failures)

        log.info(
            "Done destroying resources [%d succeeded, %d failed, %d skipped]",
            attempted - failures,
            failures,
            total - attempted,
        )

    def gather(self, collectors=None):
        start = time.perf_counter()
        if collectors is None:
            collectors = [
                *(
                    # ruff hint
                    collector(type_filters=self.type_filters)
                    for collector in self.DEFAULT_EXTRA_COLLECTORS
                ),
                *(
                    cls
                    for type_name, cls in Resource.TYPES.items()
                    if hasattr(cls, "gather")
                    if (not self.type_filters and type_name not in self.type_filters_exclude)
                    or type_name in self.type_filters
                ),
            ]

        resource_set = ResourceSet(
            # ruff hint
            resource
            for collector in collectors
            for resource in self.gather_from(collector)
        )
        end = time.perf_counter()
        log.debug("Time spent gathering before loading was %.1fs", end - start)

        for cls, resources in resource_set.iter_by_class():
            cls.load_bulk(self.client, resources)

        end = time.perf_counter()
        log.debug("Total time gathering was %.1fs", end - start)

        return resource_set

    def gather_from(self, collector):
        if isinstance(collector, type):
            log.info("Gathering %s", pluralize(collector.__name__))
        else:
            log.info("Gathering from %s", collector.__class__.__name__)

        start = time.perf_counter()
        resources = collector.gather(
            self.client,
            self.name_matcher,
            dict(self.gather_options),
        )
        end = time.perf_counter()

        log.debug("Gathered %d resources in %.1fs", len(resources), end - start)
        return resources

    def _call_delete(self, resource):
        for dependency in resource.get_dependencies():
            self._call_delete(dependency)

        log.info("Deleting %s", resource)
        resource.delete(self.client)

    def _log_resource(self, resource, level=1):
        for i, line in enumerate(resource.display(self.display_tags)):
            if i == 0:
                sep = "- "
            else:
                sep = "  "
            log.info("%s%s%s", "  " * level, sep, line)

        for dependency in resource.get_dependencies():
            self._log_resource(dependency, level + 1)


class Prompter:
    def __init__(self, auto_confirm=False):
        self.auto_confirm = auto_confirm
        self.groups = {}

    def confirm(self, prompt, group=None):
        if self.auto_confirm:
            return True

        all_groups_value = self.groups.get(None)
        if all_groups_value is not None:
            if all_groups_value == "Y":
                return True
            if all_groups_value != "P":
                return False

        group_value = self.groups.get(group)
        if group is not None:
            if group_value is None:
                raise RuntimeError(f"Group '{group}' has not been prompted yet")
            if group_value == "Y":
                return True
            if group_value != "P":
                return False

        resp = input(f"{prompt} [y/N]: ").strip().upper() or "N"
        value = resp[0]
        return value == "Y"

    def confirm_group(self, prompt, group):
        if self.auto_confirm:
            return True

        if group is not None:
            all_groups_value = self.groups.get(None)
            if all_groups_value == "Y":
                return True
            if all_groups_value != "P":
                return False

        value = self.groups.get(group)
        if value is None:
            resp = input(f"{prompt} [y/N/p]: ").strip().upper() or "N"
            value = resp[0]
            self.groups[group] = value

        return value in "YP"


class NameMatcher:
    def __init__(self, prefix, exclude=()):
        self.prefix = prefix
        self.exclude = exclude

    def matches(self, value):
        if not value.startswith(self.prefix):
            return False

        return not any(value.startswith(prefix) for prefix in self.exclude)

    def replace(self, old, new, count=-1):
        """Return a new NameMatcher with str.replace called on all string"""

        return NameMatcher(
            prefix=self.prefix.replace(old, new, count),
            exclude=tuple(ex.replace(old, new, count) for ex in self.exclude),
        )


# Copied from the python3.9 implementation.
# https://github.com/python/cpython/blob/300d3155af0cb2d0fdf3fabe2e34a0e6ec832cf0/Lib/argparse.py#L863-L901
class BooleanOptionalAction(argparse.Action):
    def __init__(
        self,
        option_strings,
        dest,
        default=None,
        type=None,
        choices=None,
        required=False,
        help=None,
        metavar=None,
    ):
        _option_strings = []
        for option_string in option_strings:
            _option_strings.append(option_string)

            if option_string.startswith("--"):
                option_string = "--no-" + option_string[2:]
                _option_strings.append(option_string)

        if help is not None and default is not None and default is not argparse.SUPPRESS:
            help += " (default: %(default)s)"

        super().__init__(
            option_strings=_option_strings,
            dest=dest,
            nargs=0,
            default=default,
            type=type,
            choices=choices,
            required=required,
            help=help,
            metavar=metavar,
        )

    def __call__(self, parser, namespace, values, option_string=None):
        if option_string in self.option_strings:
            setattr(
                namespace,
                self.dest,
                not option_string.startswith("--no-"),
            )

    def format_usage(self):
        return " | ".join(self.option_strings)


def pluralize(word):
    if word[-2:] in ("ay", "ey", "oy"):
        return word + "s"
    if word[-1:] == "y":
        return word[:-1] + "ies"
    return word + "s"


def _tag_dict(tags):
    return {tag["Key"]: tag["Value"] for tag in tags}


def _batched(iterable, n):
    # TODO(reweeden): Python3.12 adds itertools.batched. When 3.12 is MSV
    # replace this helper with itertools.batched.
    iterator = iter(iterable)
    while batch := tuple(itertools.islice(iterator, n)):
        yield batch


def _get_version() -> str:
    name = "destroy-cumulus"
    dist = Distribution.from_name(name)
    direct_url = json.loads(dist.read_text("direct_url.json"))
    editable = direct_url.get("dir_info", {}).get("editable", False)
    return f"{name} {'(editable) ' if editable else ''}{dist.version} on Python {python_version()}"


def main(args=None):
    parser = argparse.ArgumentParser(
        description="Clean up partially destroyed Cumulus stacks",
        epilog=HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    # Controlling collection
    collection_group = parser.add_argument_group(title="collection")
    collection_group.add_argument("prefix", help="Stack prefix (e.g. asf-cumulus-dev)")
    collection_group.add_argument(
        "--exclude",
        help="Stack prefixes to ignore",
        nargs="*",
        default=(),
        metavar="exclude",
    )
    collection_group.add_argument(
        "--filter",
        help=f"Filter the type of resource to destroy (e.g. --filter {Bucket.TYPE_FILTER})",
        nargs="*",
        default=(),
        choices=list(Resource.TYPES),
        metavar="filter",
    )
    collection_group.add_argument(
        "--filter-exclude",
        help="Type of resource to exclude from the filter",
        nargs="*",
        default=(),
        choices=list(Resource.TYPES),
        metavar="filter_exclude",
    )
    collection_group.add_argument(
        "--collect-all",
        "-a",
        help="Enable all extra collectors",
        action="store_true",
        default=False,
    )
    collection_group.add_argument(
        "--collect-tagged",
        help="Collect all resources with matching Deployment tag",
        action=BooleanOptionalAction,
        default=True,
    )
    collection_group.add_argument(
        "--collect-unnamed-roles",
        help="Collect IAM roles named terraform* with matching policy resources",
        action=BooleanOptionalAction,
        default=False,
    )
    collection_group.add_argument(
        "--max-items",
        help=(
            "Limit the number of items returned from the AWS API for certain "
            "resource types that support it, e.g. EventSourceMappings"
        ),
        type=int,
        default=None,
    )

    # Controlling output
    output_group = parser.add_argument_group(title="output")
    output_group.add_argument("--verbose", "-v", help="Verbosity level", action="count", default=0)
    output_group.add_argument("--tags", help="Display all resource tags", action="store_true")

    parser.add_argument("--version", action="version", version=_get_version())
    parser.add_argument("--profile", help="AWS profile")
    parser.add_argument("--yes", "-y", help="Auto confirm prompts", action="store_true", default=False)

    args = parser.parse_args(args=args)

    log.addHandler(logging.StreamHandler(sys.stdout))
    level = max(logging.INFO - args.verbose * 10, 1)
    log.setLevel(level)

    gather_options = {}
    if args.max_items:
        gather_options["MaxItems"] = args.max_items

    destroyer = CumulusDestroyer(
        profile=args.profile,
        name_matcher=NameMatcher(
            args.prefix,
            exclude=args.exclude,
        ),
        type_filters=args.filter,
        type_filters_exclude=args.filter_exclude,
        auto_confirm=args.yes,
        display_tags=args.tags,
        gather_options=gather_options,
    )

    collectors = []
    if args.collect_all or args.collect_tagged:
        collectors.append(
            TaggedResourceCollector(type_filters=args.filter),
        )
    if args.collect_all or args.collect_unnamed_roles:
        collectors.append(
            UnnamedIAMRoleCollector(type_filters=args.filter),
        )
    collectors.extend(
        cls
        for type_name, cls in Resource.TYPES.items()
        if hasattr(cls, "gather")
        if (not destroyer.type_filters and type_name not in destroyer.type_filters_exclude)
        or type_name in destroyer.type_filters
    )

    try:
        resources = destroyer.gather(collectors)
        destroyer.destroy(resources)
    except (KeyboardInterrupt, EOFError):
        log.error("\nOperation cancelled")


if __name__ == "__main__":
    main()
