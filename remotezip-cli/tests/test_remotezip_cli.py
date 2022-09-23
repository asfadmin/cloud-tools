import pytest
from remotezip_cli import main


def test_main_error():
    with pytest.raises(SystemExit):
        main()
