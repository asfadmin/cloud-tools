import argparse

import pytest
from test_cnm.config import ConfigBasic, ConfigError, ConfigFull


def test_from_file_default(data_path):
    config = ConfigBasic.from_file(data_path / "testcnm.cfg")

    assert config.profile == "sbx"
    assert config.test_bucket == "asf-cumulus-dev-tests-e2e"
    assert config._options == {}
    assert config._section == {}
    assert config._default_section == {
        "profile": "sbx",
        "test_bucket": "asf-cumulus-dev-tests-e2e",
        "cnm_ingest_queue": "asf-cumulus-dev-opera-cnm-ingest-queue",
        "cnm_response_queue": "asf-cumulus-dev-opera-mock-jpl-response-queue",
        "provider": "JPL-OPERA",
    }


def test_from_file_args_override(data_path):
    config = ConfigBasic.from_file(
        data_path / "testcnm.cfg",
        argparse.Namespace(test_bucket="override-test-bucket"),
    )

    assert config.profile == "sbx"
    assert config.test_bucket == "override-test-bucket"
    assert config._options == {
        "test_bucket": "override-test-bucket",
    }
    assert config._section == {}
    assert config._default_section == {
        "profile": "sbx",
        "test_bucket": "asf-cumulus-dev-tests-e2e",
        "cnm_ingest_queue": "asf-cumulus-dev-opera-cnm-ingest-queue",
        "cnm_response_queue": "asf-cumulus-dev-opera-mock-jpl-response-queue",
        "provider": "JPL-OPERA",
    }


def test_from_file_environment(data_path):
    config = ConfigBasic.from_file(
        data_path / "testcnm.cfg",
        argparse.Namespace(environment="sitenv"),
    )

    assert config.profile == "sit"
    assert config.test_bucket == "asf-cumulus-int-tests-e2e"
    assert config._options == {
        "environment": "sitenv",
    }
    assert config._section == {
        "profile": "sit",
        "test_bucket": "asf-cumulus-int-tests-e2e",
    }
    assert config._default_section == {
        "profile": "sbx",
        "test_bucket": "asf-cumulus-dev-tests-e2e",
        "cnm_ingest_queue": "asf-cumulus-dev-opera-cnm-ingest-queue",
        "cnm_response_queue": "asf-cumulus-dev-opera-mock-jpl-response-queue",
        "provider": "JPL-OPERA",
    }


def test_from_file_inheritance(data_path):
    config = ConfigBasic.from_file(
        [
            data_path / "home_testcnm.cfg",
            data_path / "partial_testcnm.cfg",
        ]
    )

    assert config.profile == "home-sbx"
    assert config.test_bucket == "asf-cumulus-dev-tests-e2e"
    assert config._options == {}
    assert config._section == {}
    assert config._default_section == {
        "profile": "home-sbx",
        "test_bucket": "asf-cumulus-dev-tests-e2e",
        "cnm_ingest_queue": "asf-cumulus-dev-opera-cnm-ingest-queue",
        "cnm_response_queue": "asf-cumulus-dev-opera-mock-jpl-response-queue",
        "provider": "JPL-OPERA",
    }


def test_dynamic_config(data_path):
    config = ConfigFull.from_file(data_path / "testcnm.cfg")

    config = config.dynamic_config({"cnm_ingest_queue": "foo-bar"})

    assert config.profile == "sbx"
    assert config.test_bucket == "asf-cumulus-dev-tests-e2e"
    assert config.cnm_ingest_queue == "foo-bar"
    assert config._options == {}
    assert config._section == {}
    assert config._default_section == {
        "profile": "sbx",
        "test_bucket": "asf-cumulus-dev-tests-e2e",
        "cnm_ingest_queue": "asf-cumulus-dev-opera-cnm-ingest-queue",
        "cnm_response_queue": "asf-cumulus-dev-opera-mock-jpl-response-queue",
        "provider": "JPL-OPERA",
    }


def test_dynamic_config_with_args(data_path):
    config = ConfigFull.from_file(
        data_path / "testcnm.cfg",
        argparse.Namespace(cnm_ingest_queue="cnm-ingest-queue-from-args"),
    )

    config = config.dynamic_config({"cnm_ingest_queue": "foo-bar"})

    assert config.profile == "sbx"
    assert config.test_bucket == "asf-cumulus-dev-tests-e2e"
    assert config.cnm_ingest_queue == "cnm-ingest-queue-from-args"
    assert config._options == {
        "cnm_ingest_queue": "cnm-ingest-queue-from-args",
    }
    assert config._section == {}
    assert config._default_section == {
        "profile": "sbx",
        "test_bucket": "asf-cumulus-dev-tests-e2e",
        "cnm_ingest_queue": "asf-cumulus-dev-opera-cnm-ingest-queue",
        "cnm_response_queue": "asf-cumulus-dev-opera-mock-jpl-response-queue",
        "provider": "JPL-OPERA",
    }


def test_dynamic_config_with_env(data_path):
    config = ConfigFull.from_file(
        data_path / "testcnm.cfg",
        argparse.Namespace(environment="sitenv"),
    )

    config = config.dynamic_config({"cnm_ingest_queue": "cnm-ingest-queue-from-dynamic"})

    assert config.profile == "sit"
    assert config.test_bucket == "asf-cumulus-int-tests-e2e"
    assert config.cnm_ingest_queue == "cnm-ingest-queue-from-dynamic"
    assert config._options == {
        "environment": "sitenv",
    }
    assert config._section == {
        "profile": "sit",
        "test_bucket": "asf-cumulus-int-tests-e2e",
    }
    assert config._default_section == {
        "profile": "sbx",
        "test_bucket": "asf-cumulus-dev-tests-e2e",
        "cnm_ingest_queue": "asf-cumulus-dev-opera-cnm-ingest-queue",
        "cnm_response_queue": "asf-cumulus-dev-opera-mock-jpl-response-queue",
        "provider": "JPL-OPERA",
    }


def test_dynamic_config_with_env_and_args(data_path):
    config = ConfigFull.from_file(
        data_path / "testcnm.cfg",
        argparse.Namespace(
            environment="sitenv",
            cnm_ingest_queue="cnm-ingest-queue-from-args",
        ),
    )

    config = config.dynamic_config({"cnm_ingest_queue": "cnm-ingest-queue-from-dynamic"})

    assert config.profile == "sit"
    assert config.test_bucket == "asf-cumulus-int-tests-e2e"
    assert config.cnm_ingest_queue == "cnm-ingest-queue-from-args"
    assert config._options == {
        "environment": "sitenv",
        "cnm_ingest_queue": "cnm-ingest-queue-from-args",
    }
    assert config._section == {
        "profile": "sit",
        "test_bucket": "asf-cumulus-int-tests-e2e",
    }
    assert config._default_section == {
        "profile": "sbx",
        "test_bucket": "asf-cumulus-dev-tests-e2e",
        "cnm_ingest_queue": "asf-cumulus-dev-opera-cnm-ingest-queue",
        "cnm_response_queue": "asf-cumulus-dev-opera-mock-jpl-response-queue",
        "provider": "JPL-OPERA",
    }


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
