"""
Authentication for Startup Brain.
Simple shared-credential login with cookie-based session persistence.
Auth is skipped entirely when APP_USERNAME / APP_PASSWORD env vars are not set.
"""

import hashlib
import hmac
import os
import time

import streamlit as st


# Cookie name and expiry
_COOKIE_NAME = "sb_auth_token"
_COOKIE_MAX_AGE_DAYS = 7
_COOKIE_MAX_AGE_SECONDS = _COOKIE_MAX_AGE_DAYS * 86400


def _get_credentials():
    """Return (username, password) from env/secrets, or (None, None) if not configured."""
    username = None
    password = None
    # Try st.secrets first, then env vars
    try:
        username = st.secrets.get("APP_USERNAME")
        password = st.secrets.get("APP_PASSWORD")
    except Exception:
        pass
    if not username:
        username = os.environ.get("APP_USERNAME") or None
    if not password:
        password = os.environ.get("APP_PASSWORD") or None
    return username, password


def _get_secret_key():
    """Derive a signing key from the password using PBKDF2 (never stored, deterministic)."""
    _, password = _get_credentials()
    if not password:
        # No password configured — return None to signal tokens cannot be issued
        return None
    return hashlib.pbkdf2_hmac("sha256", password.encode(), b"startup_brain_cookie_v1", 100_000)


def _create_token(username: str) -> str:
    """Create an HMAC-signed token: username|timestamp|hmac_hex."""
    key = _get_secret_key()
    if key is None:
        return ""  # Cannot issue tokens without a secret key
    timestamp = str(int(time.time()))
    payload = f"{username}|{timestamp}"
    sig = hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}|{sig}"


def _verify_token(token: str) -> bool:
    """Verify token signature and check expiry."""
    if not token:
        return False
    key = _get_secret_key()
    if key is None:
        return False  # Cannot verify tokens without a secret key
    parts = token.split("|")
    if len(parts) != 3:
        return False
    username, timestamp_str, sig = parts

    # Verify HMAC
    payload = f"{username}|{timestamp_str}"
    expected_sig = hmac.new(key, payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected_sig):
        return False

    # Check expiry
    try:
        token_time = int(timestamp_str)
    except ValueError:
        return False
    if time.time() - token_time > _COOKIE_MAX_AGE_SECONDS:
        return False

    # Check username matches
    expected_username, _ = _get_credentials()
    if expected_username and username != expected_username:
        return False

    return True


def is_authenticated() -> bool:
    """Check if the current user is authenticated via cookie, session state, or auth bypass."""
    username, password = _get_credentials()
    if not username or not password:
        # Auth not configured — only allow if explicitly opted out via DISABLE_AUTH=true
        disable_auth = os.environ.get("DISABLE_AUTH", "").lower()
        if disable_auth in ("true", "1", "yes"):
            return True
        # On Render/production, missing credentials should block access
        if os.environ.get("RENDER") or os.environ.get("PORT"):
            return False  # Production without auth — block access
        # Local dev (no RENDER env, no PORT) — allow
        return True

    # Fast path: already verified this session
    if st.session_state.get("_authenticated"):
        return True

    # Check cookie
    try:
        from streamlit_cookies_controller import CookieController
        cookies = CookieController()
        token = cookies.get(_COOKIE_NAME)
        if token and _verify_token(token):
            st.session_state._authenticated = True
            return True
    except Exception:
        pass

    return False


def render_login_page():
    """Render the login form. Call only when is_authenticated() returns False."""
    st.markdown(
        "<div style='max-width:400px;margin:4rem auto;'>",
        unsafe_allow_html=True,
    )
    st.markdown("## Startup Brain")
    st.markdown("Sign in to continue.")

    with st.form("login_form"):
        username = st.text_input("Username")
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Sign in", type="primary", use_container_width=True)

    if submitted:
        expected_user, expected_pass = _get_credentials()
        if (
            expected_user
            and expected_pass
            and hmac.compare_digest(username, expected_user)
            and hmac.compare_digest(password, expected_pass)
        ):
            # Set session state
            st.session_state._authenticated = True
            # Set cookie
            try:
                from streamlit_cookies_controller import CookieController
                cookies = CookieController()
                token = _create_token(username)
                cookies.set(_COOKIE_NAME, token, max_age=_COOKIE_MAX_AGE_SECONDS)
            except Exception:
                pass  # Cookie storage failed — session-only auth
            st.rerun()
        else:
            st.error("Invalid username or password.")

    st.markdown("</div>", unsafe_allow_html=True)
