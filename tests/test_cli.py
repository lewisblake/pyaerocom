from typer.testing import CliRunner
from pyaerocom.scripts.cli_typer import app

from pyaerocom.io.cachehandler_ungridded import CacheHandlerUngridded
from unittest import mock

from pyaerocom import tools

# from pyaerocom import __version__

import pytest

import glob
import os
import logging
import tempfile
import shutil
import pickle
import numpy as np

# import pytest

import pyaerocom  # seems extreme. double check example. should be what we are patching


logger = logging.getLogger(__name__)
runner = CliRunner()


def test_typer_runner():
    # Test the CLI version arugment
    result = runner.invoke(app, "version")
    print()
    print(f"version: {result.stdout}")

    result = runner.invoke(
        app, ["browse", "ppiaccess"]
    )  # LB: Not sure if I want to check clearcache just yet
    print(f"list:\n{result.stdout}")


# LB: Rethink this a bit, might be able to just patch() __version__ as "0.0.0"
def test_mock_version():
    with mock.patch.object(
        pyaerocom, "__version__", "0.0.0"
    ):  # adding dummy version here as mocking object
        result = runner.invoke(app, ["version"])
        assert (
            result.stdout.rstrip() == "0.0.0"
        )  # When version() method is called by CLI code, the __version__ attribute isn't the original string, it's the string we replaced with patch.object()


# @pytest.fixture(scope="session")
# def test_create_file(tmp_path):
#     tmp_dir = tmp_path / "sub"
#     tmp_dir.mkdir()
#     tmp_file = tmp_dir / "tmp.pkl"

#     tmp_array = np.zeros(10)
#     with open(tmp_file, "wb") as f:
#         pickle.dump(tmp_array, f)


# @pytest.fixture()
# def mock_cachehandlerungridded():
#     with mock.patch.object(
#         pyaerocom.io.cachehandler_ungridded, "CacheHandlerUngridded"
#     ) as mock_CacheHandlerUngridded:
#         yield mock_CacheHandlerUngridded.return_value


def test_mock_cache_dir(tmp_path):
    with mock.patch(
        "pyaerocom.io.cachehandler_ungridded.CacheHandlerUngridded"
    ) as MockCacheHandlerUngridded:
        instance = MockCacheHandlerUngridded.return_value
        instance.cache_dir(val=tmp_path)

        instance2 = CacheHandlerUngridded()

        print()
        print("INSTANCE 1:")
        print(f"{instance.cache_dir=}")

        print()
        print("INSTANCE 2:")
        print(f"{instance2.cache_dir=}")

        assert 0

        # MockCacheHandlerUngridded.return_value.cache_dir.return_value = tmp_path
        # with CacheHandlerUngridded as MockedCachehandlerUngridded:
        #     ch = MockedCacheHandlerUngridded()
        #     print()
        #     print(f"{ch.cache_dir()=}")


def test_mock_cachehandlerungridded(tmp_path):
    with mock.patch.object(CacheHandlerUngridded, "cache_dir", tmp_path):
        ch = CacheHandlerUngridded()
        print()
        print("BELOW:")
        print(f"{ch.cache_dir=}")


def test_clearcache(tmp_path):
    # pyaerocom.const.CACHEDIR

    # if not os.listdir(ch.cache_dir):
    #     print("Cache directory is empty")
    # else:
    # tmp_cache_dir = tempfile.TemporaryDirectory(dir=const.CACHEDIR)
    # tmp_dir = tmp_path / "sub"
    # tmp_dir.mkdir()

    # Create a temp pickle file
    tmp_file = tmp_path / "tmp.pkl"
    tmp_array = np.zeros(10)
    with open(tmp_file, "wb") as f:
        pickle.dump(tmp_array, f)

    # Check pytest's tmp_path is non-empty
    assert os.listdir(tmp_path)

    with mock.patch.object(CacheHandlerUngridded, "cache_dir", tmp_path):

        result = runner.invoke(app, ["clearcache"], input="y")
        # print(result.stdout)  # Testing

        assert result.exit_code == 0
        assert not os.listdir(tmp_path)

        # assert 0 # Testing
