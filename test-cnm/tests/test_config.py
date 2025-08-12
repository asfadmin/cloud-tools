import argparse

import pytest
from test_cnm.config import ConfigBasic, ConfigError, ConfigFull


def test_from_file_default(data_path):
    config = ConfigBasic.from_file(data_path / "testcnm.cfg")

    assert config.profile == "sbx"
    assert config.test_bucket == "asf-cumulus-dev-tests-e2e"


def test_from_file_args_override(data_path):
    args = argparse.Namespace()
    args.test_bucket = "override-test-bucket"
    config = ConfigBasic.from_file(data_path / "testcnm.cfg", args)

    assert config.profile == "sbx"
    assert config.test_bucket == "override-test-bucket"


def test_from_file_environment(data_path):
    args = argparse.Namespace()
    args.environment = "sitenv"
    config = ConfigBasic.from_file(data_path / "testcnm.cfg", args)

    assert config.profile == "sit"
    assert config.test_bucket == "asf-cumulus-int-tests-e2e"


def test_from_file_inheritance(data_path):
    config = ConfigBasic.from_file(
        [
            data_path / "home_testcnm.cfg",
            data_path / "partial_testcnm.cfg",
        ]
    )

    assert config.profile == "home-sbx"
    assert config.test_bucket == "asf-cumulus-dev-tests-e2e"


def test_from_file_empty(data_path):
    with pytest.raises(
        ConfigError,
        match="environment 'default' not found",
    ):
        ConfigBasic.from_file(data_path / "empty.cfg")


def test_from_file_nonexistent(data_path):
    with pytest.raises(
        ConfigError,
        match="environment 'default' not found",
    ):
        ConfigBasic.from_file(data_path / "does_not_exist.cfg")


def test_cnm_ingest_queue_name_full_no_stack_name():
    config = ConfigFull(
        profile="",
        test_bucket="",
        cnm_ingest_queue="sds-n-cumulus-dev-nisar-workflow-queue",
        cnm_response_queue="",
        provider="",
        stack_name=None,
    )

    assert config.cnm_ingest_queue_name() == "sds-n-cumulus-dev-nisar-workflow-queue"


def test_cnm_ingest_queue_name_full_stack_name_prefix():
    config = ConfigFull(
        profile="",
        test_bucket="",
        cnm_ingest_queue="sds-n-cumulus-dev-nisar-workflow-queue",
        cnm_response_queue="",
        provider="",
        stack_name="sds-n-cumulus-dev",
    )

    assert config.cnm_ingest_queue_name() == "sds-n-cumulus-dev-nisar-workflow-queue"


def test_cnm_ingest_queue_name_postfix_with_stack_name():
    config = ConfigFull(
        profile="",
        test_bucket="",
        cnm_ingest_queue="nisar-workflow-queue",
        cnm_response_queue="",
        provider="",
        stack_name="sds-n-cumulus-dev",
    )

    assert config.cnm_ingest_queue_name() == "sds-n-cumulus-dev-nisar-workflow-queue"
