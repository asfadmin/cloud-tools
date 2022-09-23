from unittest import mock

import moto
import pytest
from destroy_cumulus import (
    CumulusDestroyer,
    ElasticsearchDomain,
    Resource,
    main
)


def test_main_error():
    with pytest.raises(SystemExit):
        main()


@pytest.mark.slow
def test_destroy_all_empty_prefixs(monkeypatch):
    # Patch out unsupported types
    monkeypatch.setitem(Resource.TYPES, "es:domain", mock.create_autospec(ElasticsearchDomain))
    # Mock all is very slow. Using it as a decorator causes the slowness to
    # affect pytest collection time.
    with moto.mock_all():
        destroyer = CumulusDestroyer(profile=None, prefix="", auto_confirm=False)
        destroyer.destroy = mock.create_autospec(destroyer.destroy)

        destroyer.destroy_all()

    destroyer.destroy.assert_called_once()
