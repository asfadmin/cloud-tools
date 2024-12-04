from trigger_s3_event.template import FormatValue, replace


def test_format_value():
    assert FormatValue("foo").format(foo="bar") == "bar"
    assert FormatValue("foo").format(foo=1) == 1
    assert FormatValue("foo[1]").format(foo=[0, 1, 2]) == 1
    assert FormatValue("foo['bar']").format(foo={"bar": "baz"}) == "baz"


def test_replace():
    assert replace("foo") == "foo"
    assert replace(1) == 1
    assert replace(True) is True
    assert replace(None) is None
    assert replace([1, 2, 3]) == [1, 2, 3]
    assert replace({"foo": "bar"}) == {"foo": "bar"}
