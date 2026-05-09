"""Tests for get_backend() factory and EnvBackend ABC."""
import sys
import pytest
from unittest.mock import patch

from envedit.core.env_backend import get_backend, EnvBackend
from envedit.core.platform_unix import UnixBackend


class TestGetBackend:
    def test_returns_unix_backend_on_linux(self):
        with patch.object(sys, "platform", "linux"):
            backend = get_backend()
        assert isinstance(backend, UnixBackend)

    def test_returns_unix_backend_on_darwin(self):
        with patch.object(sys, "platform", "darwin"):
            backend = get_backend()
        assert isinstance(backend, UnixBackend)

    def test_returns_env_backend_subclass(self):
        backend = get_backend()
        assert isinstance(backend, EnvBackend)

    def test_backend_has_all_abstract_methods(self):
        backend = get_backend()
        assert callable(backend.get_user_vars)
        assert callable(backend.get_system_vars)
        assert callable(backend.get_user_path)
        assert callable(backend.get_system_path)
        assert callable(backend.apply_user_vars)
        assert callable(backend.apply_system_vars)
        assert callable(backend.apply_user_path)
        assert callable(backend.apply_system_path)
        assert callable(backend.expand_value)

    def test_cannot_instantiate_abstract_backend(self):
        with pytest.raises(TypeError):
            EnvBackend()
