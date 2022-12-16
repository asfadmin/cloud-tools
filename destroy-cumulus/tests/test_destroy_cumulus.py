import pytest
from destroy_cumulus import main


def test_main_error():
    with pytest.raises(SystemExit):
        main()
