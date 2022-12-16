from unittest import mock

import pytest
from destroy_cumulus import log, main


def test_main_error():
    with mock.patch.object(log, "setLevel", autospec=True):
        with pytest.raises(SystemExit):
            main([])
