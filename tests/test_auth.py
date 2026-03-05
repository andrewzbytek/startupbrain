"""
Unit tests for app/components/login.py — authentication and token handling.
All tests run without API keys, MongoDB, or network access.
"""

import sys
import time
from unittest.mock import MagicMock, patch

import pytest


class _AttrDict(dict):
    """A dict that supports attribute-style access, mimicking Streamlit's SessionState."""
    def __getattr__(self, key):
        try:
            return self[key]
        except KeyError:
            raise AttributeError(key)

    def __setattr__(self, key, value):
        self[key] = value

    def __delattr__(self, key):
        try:
            del self[key]
        except KeyError:
            raise AttributeError(key)


# Mock streamlit before importing app modules
mock_st = MagicMock()
mock_st.session_state = _AttrDict()
mock_st.cache_resource = lambda f: f
mock_st.secrets = MagicMock()
sys.modules.setdefault("streamlit", mock_st)
mock_st = sys.modules["streamlit"]
if not isinstance(getattr(mock_st, 'session_state', None), _AttrDict):
    mock_st.session_state = _AttrDict()

# Mock the cookies controller
mock_cookies_module = MagicMock()
sys.modules.setdefault("streamlit_cookies_controller", mock_cookies_module)

import app.components.login as login_module
from app.components.login import (
    _create_token,
    _verify_token,
    _get_credentials,
    is_authenticated,
)


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    """Reset session state and env vars before each test."""
    new_state = _AttrDict()
    mock_st.session_state = new_state
    login_module.st = mock_st
    # Clear env vars by default
    monkeypatch.delenv("APP_USERNAME", raising=False)
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    # Reset st.secrets mock
    mock_st.secrets = MagicMock()
    mock_st.secrets.get = MagicMock(return_value=None)


class TestCredentials:
    def test_no_credentials_returns_none(self):
        """When no env vars or secrets set, returns (None, None)."""
        username, password = _get_credentials()
        assert username is None
        assert password is None

    def test_env_var_credentials(self, monkeypatch):
        """Env vars provide credentials."""
        monkeypatch.setenv("APP_USERNAME", "admin")
        monkeypatch.setenv("APP_PASSWORD", "secret123")
        username, password = _get_credentials()
        assert username == "admin"
        assert password == "secret123"

    def test_secrets_credentials(self):
        """st.secrets provides credentials."""
        mock_st.secrets.get = MagicMock(side_effect=lambda k: {"APP_USERNAME": "user1", "APP_PASSWORD": "pass1"}.get(k))
        username, password = _get_credentials()
        assert username == "user1"
        assert password == "pass1"


class TestTokenCreation:
    def test_token_format(self, monkeypatch):
        """Token has format: username|timestamp|hmac."""
        monkeypatch.setenv("APP_USERNAME", "admin")
        monkeypatch.setenv("APP_PASSWORD", "secret")
        token = _create_token("admin")
        parts = token.split("|")
        assert len(parts) == 3
        assert parts[0] == "admin"
        # Timestamp should be a number
        assert parts[1].isdigit()
        # HMAC should be hex
        assert len(parts[2]) == 64  # sha256 hex length

    def test_token_verifies(self, monkeypatch):
        """A freshly created token should verify."""
        monkeypatch.setenv("APP_USERNAME", "admin")
        monkeypatch.setenv("APP_PASSWORD", "secret")
        token = _create_token("admin")
        assert _verify_token(token) is True


class TestTokenVerification:
    def test_empty_token(self, monkeypatch):
        monkeypatch.setenv("APP_USERNAME", "admin")
        monkeypatch.setenv("APP_PASSWORD", "secret")
        assert _verify_token("") is False
        assert _verify_token(None) is False

    def test_malformed_token(self, monkeypatch):
        monkeypatch.setenv("APP_USERNAME", "admin")
        monkeypatch.setenv("APP_PASSWORD", "secret")
        assert _verify_token("just-garbage") is False
        assert _verify_token("a|b") is False
        assert _verify_token("a|b|c|d") is False

    def test_tampered_signature(self, monkeypatch):
        monkeypatch.setenv("APP_USERNAME", "admin")
        monkeypatch.setenv("APP_PASSWORD", "secret")
        token = _create_token("admin")
        parts = token.split("|")
        parts[2] = "0" * 64  # Fake HMAC
        assert _verify_token("|".join(parts)) is False

    def test_wrong_username(self, monkeypatch):
        monkeypatch.setenv("APP_USERNAME", "admin")
        monkeypatch.setenv("APP_PASSWORD", "secret")
        token = _create_token("admin")
        # Change expected username
        monkeypatch.setenv("APP_USERNAME", "other_user")
        assert _verify_token(token) is False

    def test_expired_token(self, monkeypatch):
        monkeypatch.setenv("APP_USERNAME", "admin")
        monkeypatch.setenv("APP_PASSWORD", "secret")
        # Create token with old timestamp
        with patch.object(login_module.time, "time", return_value=time.time() - 8 * 86400):
            token = _create_token("admin")
        # Verify with current time — should be expired (>7 days)
        assert _verify_token(token) is False

    def test_non_numeric_timestamp(self, monkeypatch):
        monkeypatch.setenv("APP_USERNAME", "admin")
        monkeypatch.setenv("APP_PASSWORD", "secret")
        assert _verify_token("admin|notanumber|abc123") is False


class TestIsAuthenticated:
    def test_no_credentials_skips_auth(self):
        """When no credentials configured, everyone is authenticated."""
        assert is_authenticated() is True

    def test_session_state_fast_path(self, monkeypatch):
        """If _authenticated is set, skip cookie check."""
        monkeypatch.setenv("APP_USERNAME", "admin")
        monkeypatch.setenv("APP_PASSWORD", "secret")
        mock_st.session_state._authenticated = True
        assert is_authenticated() is True

    def test_no_cookie_not_authenticated(self, monkeypatch):
        """Without cookie or session state, user is not authenticated."""
        monkeypatch.setenv("APP_USERNAME", "admin")
        monkeypatch.setenv("APP_PASSWORD", "secret")
        # Cookie controller returns None
        mock_controller = MagicMock()
        mock_controller.get.return_value = None
        mock_cookies_module.CookieController.return_value = mock_controller
        assert is_authenticated() is False

    def test_valid_cookie_authenticates(self, monkeypatch):
        """Valid cookie token grants access."""
        monkeypatch.setenv("APP_USERNAME", "admin")
        monkeypatch.setenv("APP_PASSWORD", "secret")
        token = _create_token("admin")
        mock_controller = MagicMock()
        mock_controller.get.return_value = token
        mock_cookies_module.CookieController.return_value = mock_controller
        assert is_authenticated() is True
        assert mock_st.session_state.get("_authenticated") is True

    def test_invalid_cookie_rejected(self, monkeypatch):
        """Invalid cookie token does not grant access."""
        monkeypatch.setenv("APP_USERNAME", "admin")
        monkeypatch.setenv("APP_PASSWORD", "secret")
        mock_controller = MagicMock()
        mock_controller.get.return_value = "admin|0|fakesig"
        mock_cookies_module.CookieController.return_value = mock_controller
        assert is_authenticated() is False

    def test_render_env_without_credentials_blocks(self, monkeypatch):
        """Set RENDER=true env var with no credentials, is_authenticated() should return False."""
        monkeypatch.setenv("RENDER", "true")
        assert is_authenticated() is False

    def test_port_env_without_credentials_blocks(self, monkeypatch):
        """Set PORT=8501 env var with no credentials, should return False."""
        monkeypatch.setenv("PORT", "8501")
        assert is_authenticated() is False

    def test_disable_auth_bypasses(self, monkeypatch):
        """Set DISABLE_AUTH=true, should return True even without credentials."""
        monkeypatch.setenv("RENDER", "true")
        monkeypatch.setenv("DISABLE_AUTH", "true")
        assert is_authenticated() is True

    def test_disable_auth_case_insensitive(self, monkeypatch):
        """Set DISABLE_AUTH=TRUE (uppercase), should return True."""
        monkeypatch.setenv("RENDER", "true")
        monkeypatch.setenv("DISABLE_AUTH", "TRUE")
        assert is_authenticated() is True
