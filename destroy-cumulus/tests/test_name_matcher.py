from destroy_cumulus import NameMatcher


def test_prefix():
    name_matcher = NameMatcher(prefix="foo")

    assert name_matcher.matches("foo")
    assert name_matcher.matches("foobar")
    assert name_matcher.matches("foo/bar")
    assert name_matcher.matches("foo-bar")

    assert not name_matcher.matches("")
    assert not name_matcher.matches("bar")
    assert not name_matcher.matches("fo")
    assert not name_matcher.matches("far")


def test_empty_prefix():
    name_matcher = NameMatcher(prefix="")

    assert name_matcher.matches("foo")
    assert name_matcher.matches("foobar")
    assert name_matcher.matches("foo/bar")
    assert name_matcher.matches("foo-bar")

    assert name_matcher.matches("")
    assert name_matcher.matches("bar")
    assert name_matcher.matches("fo")
    assert name_matcher.matches("far")


def test_prefix_exclude():
    name_matcher = NameMatcher(
        prefix="foo",
        exclude=["foobar", "foobaz"],
    )

    assert name_matcher.matches("foo")
    assert name_matcher.matches("foo/bar")
    assert name_matcher.matches("foo-bar")

    assert not name_matcher.matches("bar")
    assert not name_matcher.matches("fo")
    assert not name_matcher.matches("far")

    # Specifically excluded names
    assert not name_matcher.matches("foobar")
    assert not name_matcher.matches("foobaz")
    assert not name_matcher.matches("foobarbaz")
    assert not name_matcher.matches("foobazbar")
    assert not name_matcher.matches("foobar-baz")
    assert not name_matcher.matches("foobar/baz")


def test_replace():
    name_matcher = NameMatcher(
        prefix="foo-",
        exclude=["foo-bar", "foo-baz"],
    )
    replaced_matcher = name_matcher.replace("-", "_")

    assert replaced_matcher.matches("foo_")
    assert replaced_matcher.matches("foo_/bar")
    assert replaced_matcher.matches("foo_-bar")

    assert not replaced_matcher.matches("fo")
    assert not replaced_matcher.matches("foo")
    assert not replaced_matcher.matches("foo-")
    assert not replaced_matcher.matches("bar")
    assert not replaced_matcher.matches("far")

    # Specifically excluded names
    assert not replaced_matcher.matches("foo_bar")
    assert not replaced_matcher.matches("foo_baz")
    assert not replaced_matcher.matches("foo_barbaz")
    assert not replaced_matcher.matches("foo_bazbar")
    assert not replaced_matcher.matches("foo_bar-baz")
    assert not replaced_matcher.matches("foo_bar/baz")
