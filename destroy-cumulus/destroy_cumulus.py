import argparse
import functools
import itertools
import logging
import sys

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

To destroy all tagged and prefixed DynamoDB tables and RDS clusters with the
prefix `some-prefix` and printing verbose output:

  destroy_cumulus.py -v some-prefix --filter dynamodb:table rds:cluster
"""

# Developer notes
#
# Resource gathering is implemented through 'collector' objects. A collector
# is any object with a `gather(get_client, prefix) -> list[Resource]` method.
# Most "Resource's are currently implemented as collectors that know how to
# find that type of resource. Usually these type of collectors should be
# finding resources by name prefix, as there is already a
# TaggedResourceCollector that can find resources by 'Deployment' tag.
#
# Resource teardown is implemented as the `delete(get_client)` method on
# 'Resource' objects. To add support for a new type of resource, just implement
# a subclass of `Resource`. The only method that is required to implement is
# `delete`, however, it is generally also a good idea to implement `gather`
# and to add the resource to the ALL_RESOURCES list of the main manager object.
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
            self.type, self.id = ident.split("/", 1)
            if self.type == "":
                # Weird special case for apigateway where arns look like this:
                # arn:aws:apigateway:us-west-2::/restapis/d36my9ab58
                self.type, self.id = self.id.split("/", 1)
            self.name = self.id
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


class Resource:
    TYPE_FILTER = object()
    TYPES = {}

    def __init_subclass__(cls):
        if cls.TYPE_FILTER is Resource.TYPE_FILTER:
            raise RuntimeError(f"'{cls.__name__}' missing 'TYPE_FILTER'")

        Resource.TYPES[cls.TYPE_FILTER] = cls

    def __init__(self, name, id, arn=None, tags=()):
        self.name = name
        self.id = id
        self.arn = arn
        self.tags = {tag["Key"]: tag["Value"] for tag in tags}

    @classmethod
    def from_arn(cls, arn, tags=()):
        return cls(arn.name, arn.id, arn=arn, tags=tags)

    def delete(self, get_client):
        """Destroy this resource"""
        raise NotImplementedError(f"Method 'delete' is not implemented for {self.__class__.__name__}")

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

    # These implementations are for de-duplicating using a set()
    # Some aws api calls don't return much information so we may not always
    # have access to the entire ARN
    def __hash__(self):
        return hash((self.__class__, self.id))

    def __eq__(self, other):
        return (self.__class__, self.id) == (other.__class__, other.id)


class TaggedResourceCollector:
    def __init__(self, type_filters=(), tag_filters=()):
        self.type_filters = type_filters
        self.tag_filters = tag_filters

    def gather(self, get_client, prefix):
        client = get_client("resourcegroupstaggingapi")
        tag_paginator = client.get_paginator("get_tag_values")
        paginator = client.get_paginator("get_resources")

        tag_filters = self.tag_filters
        if not tag_filters:
            tag_values = [
                tag
                for response in tag_paginator.paginate(Key="Deployment")
                for tag in response["TagValues"]
                if tag.startswith(prefix)
            ]

            if not tag_values:
                return []

            tag_filters = [dict(Key="Deployment", Values=tag_values)]

        entries = [
            entry
            for response in paginator.paginate(
                TagFilters=tag_filters,
                ResourceTypeFilters=self.type_filters
            )
            for entry in response["ResourceTagMappingList"]
        ]

        resources = []
        for entry in entries:
            arn = Arn(entry["ResourceARN"])

            cls = Resource.TYPES.get(arn.type_id)
            if cls is None:
                log.warning("Unhandled arn '%s' for type '%s'", arn, arn.type_id)
                continue

            resources.append(cls.from_arn(
                arn,
                tags=[tag for tag in entry.get("Tags", ()) if tag["Key"] == "Deployment"]
            ))

        return resources

#
# Resource subclasses defined in alphabetical order
#


class ApiGateway(Resource):
    TYPE_FILTER = "apigateway:restapis"

    @classmethod
    def gather(cls, get_client, prefix):
        client = get_client("apigateway")
        paginator = client.get_paginator("get_rest_apis")

        return [
            cls(
                name,
                entry["id"],
                tags=[dict(Key=k, Value=v) for k, v in entry.get("tags", {}).items()]
            )
            for response in paginator.paginate()
            for entry in response.get("items", ())
            if (name := entry["name"]).startswith(prefix)
        ]

    def delete(self, get_client):
        client = get_client("apigateway")
        client.delete_rest_api(restApiId=self.id)

    def display(self, *args, **kwargs):
        lines = super().display(*args, **kwargs)
        if self.name != self.id:
            lines[0] = "/".join((lines[0], self.id))

        return lines


class Bucket(Resource):
    TYPE_FILTER = "s3"

    @classmethod
    def gather(cls, get_client, prefix):
        client = get_client("s3")
        response = client.list_buckets()

        return [
            cls(name, name)
            for entry in response.get("Buckets", ())
            if (name := entry["Name"]).startswith(prefix)
        ]

    def delete(self, get_client):
        client = get_client("s3")
        object_paginator = client.get_paginator("list_objects_v2")
        version_paginator = client.get_paginator("list_object_versions")

        for response in version_paginator.paginate(Bucket=self.name):
            if "Versions" not in response:
                continue

            client.delete_objects(
                Bucket=self.name,
                Delete=dict(
                    Objects=[
                        {"Key": entry["Key"], "VersionId": entry["VersionId"]}
                        for entry in response["Versions"]
                    ]
                )
            )

        for response in object_paginator.paginate(Bucket=self.name):
            if "Contents" not in response:
                continue

            client.delete_objects(
                Bucket=self.name,
                Delete=dict(
                    Objects=[
                        {"Key": entry["Key"]}
                        for entry in response["Contents"]
                    ]
                )
            )

        client.delete_bucket(Bucket=self.name)


class CloudFormationStack(Resource):
    TYPE_FILTER = "cloudformation:stack"

    @classmethod
    def gather(cls, get_client, prefix):
        client = get_client("cloudformation")
        paginator = client.get_paginator("list_stacks")

        return [
            cls.from_arn(Arn(entry["StackId"]))
            for response in paginator.paginate()
            for entry in response.get("StackSummaries", ())
            if entry["StackName"].startswith(prefix)
            if entry["StackStatus"] not in ("DELETE_IN_PROGRESS", "DELETE_COMPLETE")
        ]

    def delete(self, get_client):
        client = get_client("cloudformation")
        client.delete_stack(StackName=self.name)


class CloudWatchAlarm(Resource):
    TYPE_FILTER = "cloudwatch:alarm"

    @classmethod
    def gather(cls, get_client, prefix):
        client = get_client("cloudwatch")
        paginator = client.get_paginator("describe_alarms")

        return [
            cls.from_arn(Arn(entry["AlarmArn"]))
            for response in paginator.paginate(AlarmNamePrefix=prefix)
            # NOTE: Ignoring composite alarms here
            for entry in response.get("MetricAlarms", ())
            if entry["AlarmName"].startswith(prefix)
        ]

    def delete(self, get_client):
        client = get_client("cloudwatch")
        # NOTE: Could actually do a bulk delete here
        client.delete_alarms(AlarmNames=[self.name])


class CloudWatchDashboard(Resource):
    """These are expensive: $"""

    TYPE_FILTER = "cloudwatch:dashboard"

    @classmethod
    def gather(cls, get_client, prefix):
        client = get_client("cloudwatch")
        paginator = client.get_paginator("list_dashboards")

        return [
            cls.from_arn(Arn(entry["DashboardArn"]))
            for response in paginator.paginate(DashboardNamePrefix=prefix)
            for entry in response.get("DashboardEntries", ())
            if entry["DashboardName"].startswith(prefix)
        ]

    def delete(self, get_client):
        client = get_client("cloudwatch")
        # NOTE: Could actually do a bulk delete here
        client.delete_dashboards(DashboardNames=[self.name])


class CloudWatchEventRule(Resource):
    TYPE_FILTER = "events:rule"

    @classmethod
    def gather(cls, get_client, prefix):
        client = get_client("events")
        paginator = client.get_paginator("list_rules")

        return [
            cls.from_arn(Arn(entry["Arn"]))
            for response in paginator.paginate(NamePrefix=prefix)
            for entry in response.get("Rules", ())
            if entry["Name"].startswith(prefix)
        ]

    def delete(self, get_client):
        client = get_client("events")
        paginator = client.get_paginator("list_targets_by_rule")

        for response in paginator.paginate(Rule=self.name):
            client.remove_targets(
                Rule=self.name,
                Ids=[
                    entry["Id"]
                    for entry in response["Targets"]
                ]
            )

        client.delete_rule(Name=self.name)


class CloudWatchLogGroup(Resource):
    TYPE_FILTER = "logs:log-group"

    @classmethod
    def gather(cls, get_client, prefix):
        client = get_client("logs")
        paginator = client.get_paginator("describe_log_groups")

        return [
            cls.from_arn(Arn(entry["arn"]))
            for response in paginator.paginate(logGroupNamePrefix=prefix)
            for entry in response.get("logGroups", ())
            if prefix in entry["logGroupName"]
        ]

    def delete(self, get_client):
        client = get_client("logs")
        client.delete_log_group(logGroupName=self.name)


class DynamoDBTable(Resource):
    TYPE_FILTER = "dynamodb:table"

    @classmethod
    def gather(cls, get_client, prefix):
        client = get_client("dynamodb")
        paginator = client.get_paginator("list_tables")

        return [
            cls(name, name)
            for response in paginator.paginate()
            for name in response.get("TableNames", ())
            if name.startswith(prefix)
        ]

    def delete(self, get_client):
        client = get_client("dynamodb")
        client.delete_table(TableName=self.name)


class ECSCluster(Resource):
    TYPE_FILTER = "ecs:cluster"

    @classmethod
    def gather(cls, get_client, prefix):
        client = get_client("ecs")
        paginator = client.get_paginator("list_clusters")

        return [
            cls.from_arn(arn)
            for response in paginator.paginate()
            for arn_ in response["clusterArns"]
            if (arn := Arn(arn_)).name.startswith(prefix)
        ]

    def delete(self, get_client):
        client = get_client("ecs")
        client.delete_cluster(cluster=self.name)


class ECSTaskDefinition(Resource):
    TYPE_FILTER = "ecs:task-definition"

    @classmethod
    def gather(cls, get_client, prefix):
        client = get_client("ecs")
        paginator = client.get_paginator("list_task_definitions")

        return [
            cls.from_arn(arn)
            for response in paginator.paginate()
            for arn_ in response["taskDefinitionArns"]
            if (arn := Arn(arn_)).name.startswith(prefix)
        ]

    def delete(self, get_client):
        client = get_client("ecs")
        client.deregister_task_definition(taskDefinition=str(self.arn))


class ElasticsearchDomain(Resource):
    """These are expensive: $$"""

    TYPE_FILTER = "es:domain"

    @classmethod
    def gather(cls, get_client, prefix):
        client = get_client("opensearch")

        return [
            cls(name, name)
            for entry in client.list_domain_names()["DomainNames"]
            if (name := entry["DomainName"]).startswith(prefix)
        ]

    def delete(self, get_client):
        client = get_client("opensearch")
        client.delete_domain(DomainName=self.name)


class EventSourceMapping(Resource):
    TYPE_FILTER = "lambda:event-source-mapping"

    def __init__(self, id, event_source_arn, function_arn, arn=None, tags=()):
        super().__init__(id, id, arn=arn, tags=tags)
        self.event_source_arn = event_source_arn
        self.function_arn = function_arn

    @classmethod
    def gather(cls, get_client, prefix):
        client = get_client("lambda")
        paginator = client.get_paginator("list_event_source_mappings")

        return [
            cls(entry["UUID"], Arn(entry["EventSourceArn"]), function_arn)
            for response in paginator.paginate()
            for entry in response.get("EventSourceMappings", ())
            if (function_arn := Arn(entry["FunctionArn"])).name.startswith(prefix)
        ]

    def delete(self, get_client):
        client = get_client("lambda")
        client.delete_event_source_mapping(UUID=self.id)

    def get_display_name(self):
        return f"{self.event_source_arn.name} -> {self.function_arn.name}"


class IAMInstanceProfile(Resource):
    TYPE_FILTER = "iam:instanceprofile"

    def __init__(self, name, id, roles=(), arn=None, tags=()):
        super().__init__(name, id, arn=arn, tags=tags)
        self.roles = roles

    @classmethod
    def from_arn(cls, arn, roles=(), tags=()):
        return cls(arn.name, arn.id, roles, arn=arn, tags=tags)

    @classmethod
    def gather(cls, get_client, prefix):
        client = get_client("iam")
        paginator = client.get_paginator("list_instance_profiles")

        return [
            cls.from_arn(
                Arn(entry["Arn"]),
                [role["RoleName"] for role in entry["Roles"]],
                tags=entry.get("Tags", ())
            )
            for response in paginator.paginate()
            for entry in response.get("InstanceProfiles", ())
            if entry["InstanceProfileName"].startswith(prefix)
        ]

    def delete(self, get_client):
        client = get_client("iam")

        for role in self.roles:
            client.remove_role_from_instance_profile(
                InstanceProfileName=self.name,
                RoleName=role
            )

        client.delete_instance_profile(InstanceProfileName=self.name)


class IAMPolicy(Resource):
    TYPE_FILTER = "iam:policy"

    @classmethod
    def gather(cls, get_client, prefix):
        client = get_client("iam")
        paginator = client.get_paginator("list_policies")

        return [
            cls.from_arn(Arn(entry["Arn"]), tags=entry.get("Tags", ()))
            for response in paginator.paginate(Scope="Local")
            for entry in response.get("Policies", ())
            if entry["PolicyName"].startswith(prefix)
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
                    VersionId=entry["VersionId"]
                )

        client.delete_policy(PolicyArn=str(self.arn))


class IAMRole(Resource):
    TYPE_FILTER = "iam:role"

    @classmethod
    def gather(cls, get_client, prefix):
        client = get_client("iam")
        paginator = client.get_paginator("list_roles")

        return [
            cls.from_arn(Arn(entry["Arn"]), tags=entry.get("Tags", ()))
            for response in paginator.paginate()
            for entry in response.get("Roles", ())
            if entry["RoleName"].startswith(prefix)
        ]

    def delete(self, get_client):
        client = get_client("iam")
        attached_policy_paginator = client.get_paginator("list_attached_role_policies")
        inline_policy_paginator = client.get_paginator("list_role_policies")

        for response in attached_policy_paginator.paginate(RoleName=self.name):
            for entry in response["AttachedPolicies"]:
                client.detach_role_policy(
                    RoleName=self.name,
                    PolicyArn=entry["PolicyArn"]
                )

        for response in inline_policy_paginator.paginate(RoleName=self.name):
            for policy in response["PolicyNames"]:
                client.delete_role_policy(
                    RoleName=self.name,
                    PolicyName=policy
                )

        client.delete_role(RoleName=self.name)


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
    def gather(cls, get_client, prefix):
        client = get_client("lambda")
        paginator = client.get_paginator("list_functions")

        return [
            cls.from_arn(Arn(entry["FunctionArn"]))
            for response in paginator.paginate()
            for entry in response.get("Functions", ())
            if entry["FunctionName"].startswith(prefix)
        ]

    def delete(self, get_client):
        client = get_client("lambda")
        client.delete_function(FunctionName=str(self.arn))


class LambdaLayerVersion(Resource):
    TYPE_FILTER = "lambda:layer"

    @classmethod
    def gather(cls, get_client, prefix):
        client = get_client("lambda")
        layer_paginator = client.get_paginator("list_layers")
        version_paginator = client.get_paginator("list_layer_versions")

        return [
            cls.from_arn(Arn(ventry["LayerVersionArn"]))
            for response in layer_paginator.paginate()
            for entry in response.get("Layers", ())
            if (name := entry["LayerName"]).startswith(prefix)
            for vresponse in version_paginator.paginate(LayerName=name)
            for ventry in vresponse["LayerVersions"]
        ]

    def delete(self, get_client):
        client = get_client("lambda")
        client.delete_layer_version(
            LayerName=self.name,
            VersionNumber=int(self.id)
        )

    def get_display_name(self):
        return f"{self.name}:{self.id}"

    def __hash__(self):
        return hash((self.__class__, self.id))

    def __eq__(self, other):
        return (self.__class__, self.name, self.id) == (other.__class__, other.name, other.id)


class NetworkInterface(Resource):
    TYPE_FILTER = "ec2:network-interface"

    def __init__(self, name, id, status, arn=None, tags=()):
        super().__init__(name, id, arn=arn, tags=tags)
        self.status = status

    def display(self, *args, **kwargs):
        lines = super().display(*args, **kwargs)
        lines[0] = lines[0] + f" ({self.status})"
        return lines

    def delete(self, get_client):
        client = get_client("ec2")
        client.delete_network_interface(NetworkInterfaceId=self.id)


class RDSCluster(Resource):
    TYPE_FILTER = "rds:cluster"

    @classmethod
    def gather(cls, get_client, prefix):
        client = get_client("rds")
        paginator = client.get_paginator("describe_db_clusters")

        return [
            cls(
                name,
                entry["DBClusterIdentifier"],
                arn=Arn(entry["DBClusterArn"]),
                tags=entry["TagList"]
            )
            for response in paginator.paginate()
            for entry in response.get("DBClusters", ())
            if (name := entry["DBClusterIdentifier"]).startswith(prefix)
        ]

    def delete(self, get_client):
        client = get_client("rds")
        client.delete_db_cluster(DBClusterIdentifier=self.id, SkipFinalSnapshot=True)


class RDSSubnetGroup(Resource):
    TYPE_FILTER = "rds:subgrp"

    @classmethod
    def gather(cls, get_client, prefix):
        client = get_client("rds")
        paginator = client.get_paginator("describe_db_subnet_groups")

        return [
            cls(name, entry["DBSubnetGroupId"])
            for response in paginator.paginate(
                # NOTE(04/25/22): Filters are not supported yet
                # Filters=[dict(Name="tag:Deployment", Values=[prefix + "*"])]
            )
            for entry in response.get("DBSubnetGroups", ())
            if (name := entry["DBSubnetGroupName"]).startswith(prefix)
        ]

    def delete(self, get_client):
        client = get_client("rds")
        client.delete_db_subnet_group(DBSubnetGroupName=self.name)


class Secret(Resource):
    TYPE_FILTER = "secretsmanager:secret"

    @classmethod
    def gather(cls, get_client, prefix):
        client = get_client("secretsmanager")
        paginator = client.get_paginator("list_secrets")

        return [
            cls.from_arn(Arn(entry["ARN"]), tags=entry.get("Tags", ()))
            for response in paginator.paginate()
            for entry in response.get("SecretList", ())
            if entry["Name"].startswith(prefix)
        ]

    def delete(self, get_client):
        client = get_client("secretsmanager")
        client.delete_secret(SecretId=str(self.arn), RecoveryWindowInDays=7)


class SecurityGroup(Resource):
    TYPE_FILTER = "ec2:security-group"

    def __init__(self, name, id, network_interfaces, arn=None, tags=()):
        super().__init__(name, id, arn=arn, tags=tags)
        self.network_interfaces = network_interfaces

    @classmethod
    def from_arn(cls, arn, tags=()):
        return cls(arn.name, arn.id, [], arn=arn, tags=tags)

    @classmethod
    def gather(cls, get_client, prefix):
        client = get_client("ec2")
        paginator = client.get_paginator("describe_security_groups")
        eni_paginator = client.get_paginator("describe_network_interfaces")

        return [
            cls(
                entry["GroupName"],
                entry["GroupId"],
                network_interfaces=[
                    NetworkInterface(
                        entry["Description"],
                        entry["NetworkInterfaceId"],
                        entry["Status"],
                        tags=entry["TagSet"]
                    )
                    for response in eni_paginator.paginate(
                        Filters=[dict(Name="group-id", Values=[entry["GroupId"]])]
                    )
                    for entry in response["NetworkInterfaces"]
                ],
                tags=entry.get("Tags", ())
            )
            for response in itertools.chain(
                # We need to make two separate queries because filters are 'and'ed
                paginator.paginate(
                    Filters=[dict(Name="tag:Deployment", Values=[prefix + "*"])]
                ),
                paginator.paginate(
                    Filters=[dict(Name="group-name", Values=[prefix + "*"])]
                )
            )
            for entry in response.get("SecurityGroups", ())
        ]

    def delete(self, get_client):
        client = get_client("ec2")
        client.delete_security_group(GroupId=self.id)

    def get_dependencies(self):
        return self.network_interfaces


class SNSTopic(Resource):
    TYPE_FILTER = "sns"

    @classmethod
    def gather(cls, get_client, prefix):
        client = get_client("sns")
        paginator = client.get_paginator("list_topics")

        return [
            cls.from_arn(arn)
            for response in paginator.paginate()
            for entry in response.get("Topics", ())
            if (arn := Arn(entry["TopicArn"])).name.startswith(prefix)
        ]

    def delete(self, get_client):
        client = get_client("sns")
        client.delete_topic(TopicArn=str(self.arn))


class SQSQueue(Resource):
    TYPE_FILTER = "sqs"

    @classmethod
    def gather(cls, get_client, prefix):
        client = get_client("sqs")
        paginator = client.get_paginator("list_queues")

        return [
            cls(url)
            for response in paginator.paginate(QueueNamePrefix=prefix)
            for url in response.get("QueueUrls", ())
            if url.startswith(prefix)
        ]

    def delete(self, get_client):
        client = get_client("sqs")
        client.delete_queue(QueueUrl=self.name)


class StepFunction(Resource):
    TYPE_FILTER = "states:stateMachine"

    @classmethod
    def gather(cls, get_client, prefix):
        client = get_client("stepfunctions")
        paginator = client.get_paginator("list_state_machines")

        return [
            cls.from_arn(arn)
            for response in paginator.paginate()
            for entry in response.get("stateMachines", ())
            if (arn := Arn(entry["stateMachineArn"])).name.startswith(prefix)
        ]

    def delete(self, get_client):
        client = get_client("stepfunctions")
        client.delete_state_machine(stateMachineArn=str(self.arn))


class ResourceSet:
    def __init__(self, iterable=()):
        self._resources = {}
        for item in iterable:
            self.add(item)

    def add(self, resource):
        if resource in self._resources:
            log.debug(
                "Updating already found [%s] %s",
                resource.__class__.__name__,
                resource.name
            )
            old = self._resources.pop(resource)
            resource.tags.update(old.tags)

        self._resources[resource] = resource

    def __iter__(self):
        return iter(self._resources.values())


class CumulusDestroyer:
    # Resources will be destroyed in the order they are defined here, so put
    # dependent resources towards the end.
    ALL_RESOURCES = [
        CloudFormationStack,
        ApiGateway,
        LambdaFunction,
        LambdaLayerVersion,
        EventSourceMapping,
        IAMInstanceProfile,
        IAMRole,
        IAMPolicy,
        CloudWatchDashboard,
        CloudWatchAlarm,
        CloudWatchEventRule,
        CloudWatchLogGroup,
        ElasticsearchDomain,
        SNSTopic,
        SQSQueue,
        DynamoDBTable,
        RDSCluster,
        RDSSubnetGroup,
        ECSCluster,
        ECSTaskDefinition,
        SecurityGroup,
        Secret,
        Bucket,
    ]

    # Other ways to search for matching resources
    OTHER_COLLECTORS = [
        TaggedResourceCollector
    ]

    SORT_KEY = {cls: i for i, cls in enumerate(ALL_RESOURCES)}

    def __init__(self, profile, prefix, auto_confirm=False):
        self.session = boto3.Session(profile_name=profile)
        self.prefix = prefix
        self.auto_confirm = auto_confirm
        # Prompt for confirmations on a more granular level
        self.pick_confirm = False

    @functools.lru_cache()
    def client(self, *args, **kwargs):
        return self.session.client(*args, **kwargs)

    def destroy_all(self):
        collectors = [
            *(cls() for cls in self.OTHER_COLLECTORS),
            *(
                resource for resource in self.ALL_RESOURCES
                if hasattr(resource, "gather")
            )
        ]

        resources = ResourceSet(
            resource
            for collector in collectors
            for resource in self.gather(collector)
        )

        self.destroy(resources)

    def destroy_one(self, cls):
        resources = self.gather(cls)
        if not resources:
            return

        self.destroy(resources)

    def destroy(self, resources):
        resources = sorted(
            resources,
            key=lambda res: (
                self.SORT_KEY.get(res.__class__, len(Resource.TYPES)),
                res.__class__.__name__,
                res.tags.get("Deployment", ""),
                res.get_display_name()
            )
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
            total - attempted
        )

    def gather(self, collector):
        if isinstance(collector, type):
            log.info("Gathering %s", pluralize(collector.__name__))
        else:
            log.info("Gathering from %s", collector.__class__.__name__)

        resources = collector.gather(self.client, self.prefix)
        log.debug("Gathered %d resources", len(resources))
        return resources

    def _call_delete(self, resource):
        for dependency in resource.get_dependencies():
            self._call_delete(dependency)

        log.info("Deleting %s", resource)
        resource.delete(self.client)

    def _log_resource(self, resource, level=1):
        for i, line in enumerate(resource.display()):
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


def pluralize(word):
    if word[-2:] == "cy":
        return word[:-1] + "ies"
    return word + "s"


def main():
    all_resources = {
        type_name: cls
        for type_name, cls in Resource.TYPES.items()
    }

    parser = argparse.ArgumentParser(
        description="Clean up partially destroyed Cumulus stacks",
        epilog=HELP,
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("prefix", help="Stack prefix (e.g. asf-cumulus-dev)")
    parser.add_argument(
        "--filter",
        help="Filter the type of resource to destroy (e.g. --filter s3:bucket)",
        nargs="*",
        choices=all_resources.keys(),
        metavar="filters"
    )
    parser.add_argument("--profile", help="AWS profile")
    parser.add_argument("--verbose", "-v", help="Verbosity level", action="count", default=0)
    parser.add_argument("--yes", "-y", help="Auto confirm prompts", action="store_true", default=False)

    args = parser.parse_args()

    log.addHandler(logging.StreamHandler(sys.stdout))
    level = max(logging.INFO - args.verbose * 10, 0)
    log.setLevel(level)

    destroyer = CumulusDestroyer(
        profile=args.profile,
        prefix=args.prefix,
        auto_confirm=args.yes
    )
    try:
        if not args.filter:
            destroyer.destroy_all()
        else:
            collector = TaggedResourceCollector(
                type_filters=args.filter,
            )
            resources = ResourceSet(
                resource
                for resource in (
                    *destroyer.gather(collector),
                    *(
                        resource
                        for resource_type in args.filter
                        if hasattr(all_resources[resource_type], "gather")
                        for resource in destroyer.gather(all_resources[resource_type])
                    )
                )
            )
            destroyer.destroy(resources)

    except (KeyboardInterrupt, EOFError):
        log.error("\nOperation cancelled")


if __name__ == "__main__":
    main()
