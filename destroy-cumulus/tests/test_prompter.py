from unittest import mock

from destroy_cumulus import Prompter


@mock.patch("destroy_cumulus.input")
def test_prompter(mock_input):
    prompter = Prompter(auto_confirm=False)

    # Enter pick mode
    mock_input.return_value = "P"
    assert prompter.confirm_group("", None) is True

    # Take everything in group 1
    mock_input.return_value = "Y"
    assert prompter.confirm_group("", "Group 1") is True

    mock_input.reset_mock()
    assert prompter.confirm("Group 1 - Item 1", "Group 1") is True
    assert prompter.confirm("Group 1 - Item 2", "Group 1") is True
    assert prompter.confirm("Group 1 - Item 3", "Group 1") is True
    mock_input.assert_not_called()

    # Take nothing from group 2
    mock_input.return_value = "N"
    assert prompter.confirm_group("", "Group 2") is False

    mock_input.reset_mock()
    assert prompter.confirm("Group 2 - Item 1", "Group 2") is False
    assert prompter.confirm("Group 2 - Item 2", "Group 2") is False
    assert prompter.confirm("Group 2 - Item 3", "Group 2") is False
    mock_input.assert_not_called()

    # Pick from group 3
    mock_input.return_value = "P"
    assert prompter.confirm_group("", "Group 3") is True

    mock_input.return_value = "Y"
    assert prompter.confirm("Group 3 - Item 1", "Group 3") is True
    mock_input.return_value = "N"
    assert prompter.confirm("Group 3 - Item 2", "Group 3") is False
    mock_input.return_value = "P"
    assert prompter.confirm("Group 3 - Item 3", "Group 3") is False
    mock_input.return_value = "Y"
    assert prompter.confirm("Group 3 - Item 4", "Group 3") is True


@mock.patch("destroy_cumulus.input")
def test_prompter_confirm(mock_input):
    prompter = Prompter(auto_confirm=False)

    mock_input.return_value = "Y"
    assert prompter.confirm("") is True

    mock_input.return_value = "N"
    assert prompter.confirm("") is False

    mock_input.return_value = ""
    assert prompter.confirm("") is False

    mock_input.return_value = "foobar"
    assert prompter.confirm("") is False


@mock.patch("destroy_cumulus.input")
def test_prompter_confirm_group_yes(mock_input):
    prompter = Prompter(auto_confirm=False)

    mock_input.return_value = "Y"
    assert prompter.confirm_group("", None) is True
    mock_input.reset_mock()

    mock_input.return_value = "N"
    assert prompter.confirm_group("", None) is True
    mock_input.assert_not_called()
    assert prompter.confirm_group("", None) is True
    mock_input.assert_not_called()


@mock.patch("destroy_cumulus.input")
def test_prompter_confirm_group_no(mock_input):
    prompter = Prompter(auto_confirm=False)

    mock_input.return_value = "N"
    assert prompter.confirm_group("", None) is False
    mock_input.reset_mock()

    mock_input.return_value = "Y"
    assert prompter.confirm_group("", None) is False
    mock_input.assert_not_called()
    assert prompter.confirm_group("", None) is False
    mock_input.assert_not_called()


@mock.patch("destroy_cumulus.input")
def test_prompter_confirm_group_pick(mock_input):
    prompter = Prompter(auto_confirm=False)

    mock_input.return_value = "P"
    assert prompter.confirm_group("", None) is True
    mock_input.reset_mock()

    mock_input.return_value = "N"
    assert prompter.confirm_group("", None) is True
    mock_input.assert_not_called()
    assert prompter.confirm_group("", None) is True
    mock_input.assert_not_called()


@mock.patch("destroy_cumulus.input")
def test_prompter_confirm_group_default_group(mock_input):
    prompter = Prompter(auto_confirm=False)

    mock_input.return_value = "N"
    assert prompter.confirm_group("", None) is False
    mock_input.reset_mock()

    mock_input.return_value = "Y"
    assert prompter.confirm_group("", "Group 2") is False
    mock_input.assert_not_called()
    assert prompter.confirm_group("", "Group 3") is False
    mock_input.assert_not_called()
