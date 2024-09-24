from destroy_cumulus import Bucket, LambdaFunction, ResourceSet


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
        resource
        for _, resources in resource_set.iter_by_class()
        for resource in resources
    ]
    assert len(resource_list) == 1
    assert resource_list[0].tags == {
        "foo": "foo",
        "bar": "bar",
    }


def test_iter_by_class():
    resource_set = ResourceSet()

    resource_set.add(Bucket("foo", "foo"))
    resource_set.add(Bucket("bar", "bar"))

    resource_set.add(LambdaFunction("test-lambda", "test-lambda"))

    assert list(resource_set.iter_by_class()) == [
        (Bucket, {Bucket("foo", "foo"), Bucket("bar", "bar")}),
        (LambdaFunction, {LambdaFunction("test-lambda", "test-lambda")}),
    ]
