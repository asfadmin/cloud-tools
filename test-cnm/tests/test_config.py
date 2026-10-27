import argparse
from unittest import mock

import pytest
from test_cnm.config import ConfigBasic, ConfigError, ConfigFull, _get_session


@pytest.fixture(autouse=True)
def clear_session_cache():
    _get_session.cache_clear()


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


def test_response_session_defaults_to_session(monkeypatch):
    config = ConfigFull(
        profile="sbx",
        test_bucket="",
        cnm_ingest_queue="",
        cnm_response_queue="",
        provider="",
    )
    session = mock.Mock()
    monkeypatch.setattr(config, "session", session)

    assert config.response_session() is session.return_value
    session.assert_called_once_with()


def test_response_session_uses_response_profile(monkeypatch):
    session_cls = mock.Mock()
    monkeypatch.setattr("test_cnm.config.boto3.Session", session_cls)
    config = ConfigFull(
        profile="sbx",
        response_profile="response_profile",
        response_stack_name="cnsld-cumulus-uat2",
        test_bucket="",
        cnm_ingest_queue="",
        cnm_response_queue="",
        provider="",
    )

    assert config.response_session() is session_cls.return_value
    session_cls.assert_called_once_with(profile_name="response_profile")


def test_cnm_response_queue_name_uses_stack_name_by_default():
    config = ConfigFull(
        test_bucket="",
        cnm_ingest_queue="",
        cnm_response_queue="aria-mock-response-queue",
        provider="",
        stack_name="asf-cumulus-test",
    )

    assert config.cnm_response_queue_name() == "asf-cumulus-test-aria-mock-response-queue"


def test_cnm_response_queue_name_response_stack_name():
    config = ConfigFull(
        test_bucket="",
        cnm_ingest_queue="aria-workflow-queue",
        cnm_response_queue="aria-mock-response-queue",
        provider="",
        stack_name="asf-cumulus-test",
        response_stack_name="cnsld-cumulus-uat2",
    )

    assert config.cnm_ingest_queue_name() == "asf-cumulus-test-aria-workflow-queue"
    assert config.cnm_response_queue_name() == "cnsld-cumulus-uat2-aria-mock-response-queue"


def test_cnm_response_queue_name_response_stack_name_prefix():
    config = ConfigFull(
        test_bucket="",
        cnm_ingest_queue="",
        cnm_response_queue="cnsld-cumulus-uat2-aria-mock-response-queue",
        provider="",
        stack_name="asf-cumulus-test",
        response_stack_name="cnsld-cumulus-uat2",
    )

    assert config.cnm_response_queue_name() == "cnsld-cumulus-uat2-aria-mock-response-queue"


def test_response_session_response_profile_requires_response_stack_name():
    config = ConfigFull(
        test_bucket="",
        cnm_ingest_queue="",
        cnm_response_queue="",
        provider="",
        response_profile="response_profile",
    )

    with pytest.raises(ConfigError, match="must be set together"):
        config.response_session()


def test_response_session_response_stack_name_requires_response_profile():
    config = ConfigFull(
        test_bucket="",
        cnm_ingest_queue="",
        cnm_response_queue="",
        provider="",
        response_stack_name="cnsld-cumulus-uat2",
    )

    with pytest.raises(ConfigError, match="must be set together"):
        config.response_session()
