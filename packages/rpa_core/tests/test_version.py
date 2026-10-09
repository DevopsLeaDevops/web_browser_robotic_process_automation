from importlib.metadata import version

import rpa_core


def test_version_matches_package_metadata() -> None:
    assert rpa_core.__version__ == version("rpa-core")
