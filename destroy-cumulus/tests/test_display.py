from destroy_cumulus import NetworkInterface


def test_display_network_interface_no_description():
    resource = NetworkInterface("", "eni-0899de89cbd073900", "in-use")

    assert resource.display() == [
        "[NetworkInterface] eni-0899de89cbd073900 (in-use)"
    ]
