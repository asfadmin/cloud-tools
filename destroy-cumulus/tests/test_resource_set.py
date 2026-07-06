from destroy_cumulus import (
    Bucket,
    LambdaFunction,
    NetworkInterface,
    RDSCluster,
    RDSClusterInstance,
    ResourceSet,
    SecurityGroup,
)


def test_add_tag_merge():
    resource_set = ResourceSet()

    resource_set.add(
        Bucket("foo", "foo", tags=[{"Key": "foo", "Value": "foo"}]),
    )
    resource_set.add(
        Bucket("foo", "foo", tags=[{"Key": "bar", "Value": "bar"}]),
    )

    resource_list = list(resource_set)
    assert len(resource_list) == 1
    assert resource_list[0].tags == {
        "foo": "foo",
        "bar": "bar",
    }

    resource_list = [
        # ruff hint
        resource
        for _, resources in resource_set.iter_by_class()
        for resource in resources
    ]
    assert len(resource_list) == 1
    assert resource_list[0].tags == {
        "foo": "foo",
        "bar": "bar",
    }


def test_add_dependencies():
    resource_set = ResourceSet()

    instance = RDSClusterInstance("foo", "foo")
    cluster = RDSCluster(
        "bar",
        "bar",
        db_instances=[instance],
    )

    resource_set.add(instance)
    resource_set.add(cluster)
    resource_set.add(instance)

    assert list(resource_set) == [cluster]


def test_resolve_dependencies():
    resource_set = ResourceSet()

    instance = RDSClusterInstance("foo", "foo")
    cluster = RDSCluster(
        "bar",
        "bar",
        db_instances=[],
    )

    resource_set.add(instance)
    resource_set.add(cluster)

    assert list(resource_set) == [instance, cluster]

    cluster.db_instances.append(instance)
    resource_set.resolve_dependencies()

    assert list(resource_set) == [cluster]


def test_iter_by_class():
    resource_set = ResourceSet()

    resource_set.add(Bucket("foo", "foo"))
    resource_set.add(Bucket("bar", "bar"))

    resource_set.add(LambdaFunction("test-lambda", "test-lambda"))

    assert list(resource_set.iter_by_class()) == [
        (Bucket, {Bucket("foo", "foo"), Bucket("bar", "bar")}),
        (LambdaFunction, {LambdaFunction("test-lambda", "test-lambda")}),
    ]


def test_iter_by_class_dependencies():
    resource_set = ResourceSet()

    security_group_1 = SecurityGroup(
        "foo",
        "foo",
        network_interfaces=[
            NetworkInterface("bar", "bar", state="available"),
            NetworkInterface("baz", "baz", state="available"),
        ],
    )
    security_group_2 = SecurityGroup(
        "qux",
        "qux",
        network_interfaces=[
            NetworkInterface("bar", "bar", state="available"),
            NetworkInterface("spam", "spam", state="available"),
        ],
    )

    resource_set.add(security_group_1)
    resource_set.add(security_group_2)

    assert list(resource_set.iter_by_class()) == [
        (SecurityGroup, {security_group_1, security_group_2}),
        (
            NetworkInterface,
            {
                NetworkInterface("bar", "bar", state="available"),
                NetworkInterface("baz", "baz", state="available"),
                NetworkInterface("spam", "spam", state="available"),
            },
        ),
    ]
