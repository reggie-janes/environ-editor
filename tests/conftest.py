"""Shared pytest fixtures."""
import os
import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


@pytest.fixture(scope="session")
def qapp_args():
    return ["--platform", "offscreen"]
