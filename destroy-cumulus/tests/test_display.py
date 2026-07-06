from destroy_cumulus import Arn, EventSourceMapping, NetworkInterface


def test_display_network_interface_no_description():
    resource = NetworkInterface("", "eni-0899de89cbd073900", state="in-use")

    assert resource.display() == [
        "[NetworkInterface] eni-0899de89cbd073900 (in-use)",
    ]


def test_display_event_source_mapping_no_arns():
    resource = EventSourceMapping("6d80b9f9-68b8-4540-8a68-9f3f5468c584")

    assert resource.display() == [
        "[EventSourceMapping] 6d80b9f9-68b8-4540-8a68-9f3f5468c584",
    ]


def test_display_event_source_mapping_no_function_arn():
    resource = EventSourceMapping(
        "6d80b9f9-68b8-4540-8a68-9f3f5468c584",
        event_source_arn=Arn("arn:aws:lambda:us-west-2:123456789012:event-source-mapping/mapping-name"),
    )

    assert resource.display() == [
        "[EventSourceMapping] mapping-name -> ????",
    ]


def test_display_event_source_mapping_no_event_source_arn():
    resource = EventSourceMapping(
        "6d80b9f9-68b8-4540-8a68-9f3f5468c584",
        function_arn=Arn("arn:aws:lambda:us-west-2:123456789012:event-source-mapping/mapping-name"),
    )

    assert resource.display() == [
        "[EventSourceMapping] ???? -> mapping-name",
    ]
