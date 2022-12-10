import pytest
from destroy_cumulus import pluralize


@pytest.mark.parametrize("inp,out", (
    ("Foo", "Foos"),
    ("Bucket", "Buckets"),
    ("Stack", "Stacks"),
    ("Queue", "Queues")
))
def test_easy(inp, out):
    assert pluralize(inp) == out


@pytest.mark.parametrize("inp,out", (
    ("Policy", "Policies"),
    ("Activity", "Activities"),
    ("Category", "Categories"),
    ("Copy", "Copies")
))
def test_ies(inp, out):
    assert pluralize(inp) == out


@pytest.mark.parametrize("inp,out", (
    ("Gateway", "Gateways"),
    ("Key", "Keys"),
    ("Toy", "Toys"),
))
def test_ys(inp, out):
    assert pluralize(inp) == out
