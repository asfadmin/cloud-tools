from unittest.mock import mock_open, patch

from ctorm.config import ConfigError, CtormConfig, CtormPipeline


def test_ctorm_bucket_initialization():
    bucket = CtormPipeline(bucketname="test_bucket", share=50, ummg_prefix="test_prefix/")

    assert bucket.bucketname == "test_bucket"
    assert bucket.share == 50
    assert bucket.ummg_prefix == "test_prefix/"
    assert bucket.next_cont_token is None


def test_ctorm_config_from_file_success():
    mock_data = """
    [ctorm]
    source_buckets = [{"bucketname": "test_bucket", "share": 50}]
    granules_sqs_queue_url = "https://sqs.queue.url/"
    """
    with patch("builtins.open", mock_open(read_data=mock_data)), patch("tomllib.load") as mock_toml:
        mock_toml.return_value = {
            "ctorm": {
                "source_buckets": [{"bucketname": "test_bucket", "share": 50}],
                "granules_sqs_queue_url": "https://sqs.queue.url/",
            }
        }
        config = CtormConfig.from_file("test.cfg")

        assert config.granules_sqs_queue_url == "https://sqs.queue.url/"
        assert len(config.source_buckets) == 1
        assert isinstance(config.source_buckets[0], CtormPipeline)
        assert config.source_buckets[0].bucketname == "test_bucket"


def test_ctorm_config_from_file_missing_section():
    mock_data = "{}"
    with patch("builtins.open", mock_open(read_data=mock_data)), patch("tomllib.load") as mock_toml:
        mock_toml.return_value = {}
        try:
            CtormConfig.from_file("test.cfg")
        except ConfigError as e:
            assert str(e) == "No 'ctorm' section in config file"
