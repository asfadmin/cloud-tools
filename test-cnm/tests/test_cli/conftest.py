import configparser
import io
import logging

import pytest


@pytest.fixture(autouse=True)
def home_directory(tmp_path, test_bucket, monkeypatch):
    home_path = tmp_path / "home"
    home_path.mkdir()

    monkeypatch.setenv("HOME", str(home_path.absolute()))

    config_file = home_path / "testcnm.cfg"
    config = configparser.ConfigParser()
    config["default"] = {
        "test_bucket": test_bucket.name,
        "provider": "UNIT-TEST",
    }
    with open(config_file, "w") as f:
        config.write(f)

    return home_path


@pytest.fixture
def capcli():
    root_logger = logging.getLogger()
    buf = io.StringIO()
    handler = logging.StreamHandler(buf)
    root_logger.addHandler(handler)

    yield buf

    root_logger.removeHandler(handler)
