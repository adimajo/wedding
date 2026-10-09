"""Optional integration with a Lychee photo gallery (https://lycheeorg.dev).

Every guest gets a Lychee account whose name and password are *derived* from the guest and ``SECRET_KEY``
(nothing sensitive is stored), so the site can log guests in to the gallery with a single click.

Only the legacy ``/api/<Operation>`` endpoints are implemented (Lychee 4/5); they are kept in the constants below
so that adapting them to another version is a one-line change. The integration is disabled unless ``LYCHEE_URL``
is set.
"""

import hashlib
import hmac
from urllib.parse import unquote

import requests
from django.conf import settings
from django.utils.text import slugify

LOGIN_ENDPOINT = "Session::login"
CREATE_USER_ENDPOINT = "Users::create"
CSRF_COOKIE = "XSRF-TOKEN"  # noqa: S105
CSRF_HEADER = "X-XSRF-TOKEN"
COOKIES_FOR_BROWSER = ("XSRF-TOKEN", "lychee_session")


class LycheeError(Exception):
    """The gallery refused or could not handle a request."""


def is_enabled():
    return bool(settings.LYCHEE_URL)


def lychee_username(guest):
    """Gallery user name of a guest: readable, ASCII and unique (suffixed by the guest id)."""
    parts = [slugify(part) for part in (guest.first_name, guest.last_name) if part]
    return ".".join([*parts, str(guest.pk)])


def lychee_password(guest):
    """Gallery password of a guest, derived from ``SECRET_KEY`` (changing the key invalidates all of them)."""
    digest = hmac.new(settings.SECRET_KEY.encode(), f"lychee:{guest.pk}".encode(), hashlib.sha256)
    return digest.hexdigest()[:32]


class LycheeClient:
    """Minimal client for the Lychee JSON API."""

    def __init__(self, base_url=None, session=None, timeout=10):
        self.base_url = (base_url or settings.LYCHEE_API_URL).rstrip("/")
        self.session = session or requests.Session()
        self.timeout = timeout
        self._csrf_initialised = False

    def _init_csrf(self):
        if self._csrf_initialised:
            return
        self.session.get(self.base_url + "/", timeout=self.timeout)
        self._csrf_initialised = True
        self._sync_csrf_header()

    def _sync_csrf_header(self):
        token = self.session.cookies.get(CSRF_COOKIE)
        if token:
            self.session.headers[CSRF_HEADER] = unquote(token).replace("=", "")

    def post(self, endpoint, payload):
        try:
            self._init_csrf()
            self.session.headers["Accept"] = "application/json, text/javascript, */*; q=0.01"
            response = self.session.post(f"{self.base_url}/api/{endpoint}", json=payload, timeout=self.timeout)
        except requests.RequestException as exc:
            raise LycheeError(f"Gallery unreachable: {exc}") from exc
        self._sync_csrf_header()
        if not response.ok or response.text.strip() in {"false", ""}:
            raise LycheeError(f"{endpoint} failed with HTTP {response.status_code}")
        return response

    def login(self, username, password):
        return self.post(LOGIN_ENDPOINT, {"username": username, "password": password})

    def create_user(self, username, password):
        return self.post(
            CREATE_USER_ENDPOINT,
            {"username": username, "password": password, "may_upload": True, "may_edit_own_settings": False},
        )

    def browser_cookies(self):
        """Cookies to forward to the visitor's browser after a successful log-in."""
        return {name: self.session.cookies[name] for name in COOKIES_FOR_BROWSER if name in self.session.cookies}


def admin_client():
    """A client logged in with the gallery administrator configured in the settings."""
    if not (settings.LYCHEE_ADMIN_USER and settings.LYCHEE_ADMIN_PASSWORD):
        raise LycheeError("LYCHEE_ADMIN_USER and LYCHEE_ADMIN_PASSWORD must be set")
    client = LycheeClient()
    client.login(settings.LYCHEE_ADMIN_USER, settings.LYCHEE_ADMIN_PASSWORD)
    return client


def login_guest(guest):
    """Log a guest in to the gallery; returns the cookies to give to the browser."""
    client = LycheeClient()
    client.login(lychee_username(guest), lychee_password(guest))
    return client.browser_cookies()
