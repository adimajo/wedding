from io import StringIO
from unittest import mock

import requests
from django.core.management import CommandError, call_command

from bigday.test_utils import AppTestCase
from guests import lychee
from guests.models import Guest
from guests.tests.helpers import make_event, make_family

GALLERY = "https://wedding.example.org/photos"


class FakeResponse:
    def __init__(self, text="{}", ok=True, status_code=200):
        self.text, self.ok, self.status_code = text, ok, status_code


class FakeSession:
    """Just enough of requests.Session for the client."""

    def __init__(self, post_response=None, error=None):
        self.cookies = {}
        self.headers = {}
        self.posts = []
        self.gets = []
        self.post_response = post_response or FakeResponse()
        self.error = error

    def get(self, url, timeout):
        self.gets.append(url)
        self.cookies["XSRF-TOKEN"] = "csrf%3D%3D"
        return FakeResponse()

    def post(self, url, json, timeout):
        if self.error:
            raise self.error
        self.posts.append((url, json))
        self.cookies["lychee_session"] = "session-value"
        return self.post_response


class LycheeNamesTest(AppTestCase):
    def test_username_is_ascii_and_unique(self):
        first = Guest.objects.create_user("Éloïse", "Du Pont", "a@example.org")
        second = Guest.objects.create_user("Éloïse", "Du Pont", "b@example.org")
        self.assertEqual(lychee.lychee_username(first), f"eloise.du-pont.{first.pk}")
        self.assertNotEqual(lychee.lychee_username(first), lychee.lychee_username(second))

    def test_password_is_stable_per_guest_and_depends_on_the_secret(self):
        guest = Guest.objects.create_user("Ned", "Stark", "ned@winterfell.example")
        other = Guest.objects.create_user("Cat", "Stark", "cat@winterfell.example")
        password = lychee.lychee_password(guest)
        self.assertEqual(password, lychee.lychee_password(guest))
        self.assertNotEqual(password, lychee.lychee_password(other))
        self.assertEqual(len(password), 32)
        with self.settings(SECRET_KEY="another-secret"):
            self.assertNotEqual(password, lychee.lychee_password(guest))


class LycheeClientTest(AppTestCase):
    def test_login_posts_to_the_api_after_initialising_csrf(self):
        session = FakeSession()
        client = lychee.LycheeClient(GALLERY + "/", session=session)
        client.login("user", "pass")
        self.assertEqual(session.gets, [GALLERY + "/"])
        self.assertEqual(session.posts, [(GALLERY + "/api/Session::login", {"username": "user", "password": "pass"})])
        self.assertEqual(session.headers["X-XSRF-TOKEN"], "csrf")
        self.assertIn("application/json", session.headers["Accept"])
        self.assertEqual(client.browser_cookies(), {"XSRF-TOKEN": "csrf%3D%3D", "lychee_session": "session-value"})

    def test_server_side_calls_can_use_an_internal_address(self):
        session = FakeSession()
        with self.settings(LYCHEE_URL=GALLERY, LYCHEE_API_URL="http://192.0.2.10"):
            lychee.LycheeClient(session=session).login("user", "pass")
        self.assertEqual(session.gets, ["http://192.0.2.10/"])
        self.assertEqual(session.posts[0][0], "http://192.0.2.10/api/Session::login")

    def test_create_user_payload(self):
        session = FakeSession()
        lychee.LycheeClient(GALLERY, session=session).create_user("user", "pass")
        url, payload = session.posts[0]
        self.assertTrue(url.endswith("/api/Users::create"))
        self.assertEqual(
            payload, {"username": "user", "password": "pass", "may_upload": True, "may_edit_own_settings": False}
        )

    def test_refusals_and_network_errors_become_lychee_errors(self):
        for session in (
            FakeSession(FakeResponse("false")),
            FakeSession(FakeResponse("nope", ok=False, status_code=403)),
            FakeSession(error=requests.ConnectionError("down")),
        ):
            with self.subTest(session.post_response.text), self.assertRaises(lychee.LycheeError):
                lychee.LycheeClient(GALLERY, session=session).login("user", "pass")

    def test_login_guest_uses_the_derived_credentials(self):
        guest = Guest.objects.create_user("Ned", "Stark", "ned@winterfell.example")
        session = FakeSession()
        with self.settings(LYCHEE_URL=GALLERY), mock.patch("requests.Session", return_value=session):
            cookies = lychee.login_guest(guest)
        _, payload = session.posts[0]
        self.assertEqual(
            payload, {"username": lychee.lychee_username(guest), "password": lychee.lychee_password(guest)}
        )
        self.assertEqual(cookies["lychee_session"], "session-value")

    def test_admin_client_needs_credentials(self):
        with self.settings(LYCHEE_URL=GALLERY, LYCHEE_ADMIN_USER="", LYCHEE_ADMIN_PASSWORD=""):
            with self.assertRaises(lychee.LycheeError):
                lychee.admin_client()


class SyncLycheeUsersTest(AppTestCase):
    def setUp(self):
        self.event = make_event()
        self.other = make_event("party", "Fête")
        (self.ned,) = make_family(self.event, ("Ned", "Stark", "ned@winterfell.example"))
        (self.tyrion,) = make_family(self.other, ("Tyrion", "Lannister", "t@c.example"), family="Lannisters")

    def test_requires_a_configured_gallery(self):
        with self.assertRaisesMessage(CommandError, "LYCHEE_URL"):
            call_command("sync_lychee_users")

    def test_dry_run_lists_without_connecting(self):
        out = StringIO()
        with self.settings(LYCHEE_URL=GALLERY), mock.patch("requests.Session") as session:
            call_command("sync_lychee_users", "--dry-run", stdout=out)
        session.assert_not_called()
        self.assertIn(f"would create {lychee.lychee_username(self.ned.guest)}", out.getvalue())

    def test_creates_one_account_per_guest_of_the_event_and_reports_refusals(self):
        out, err = StringIO(), StringIO()
        client = mock.Mock()
        client.create_user.side_effect = [None, None, lychee.LycheeError("exists")]
        with (
            self.settings(LYCHEE_URL=GALLERY, LYCHEE_ADMIN_USER="admin", LYCHEE_ADMIN_PASSWORD="pw"),
            mock.patch.object(lychee, "admin_client", return_value=client),
        ):
            call_command("sync_lychee_users", "--event", "ceremony", stdout=out)
            self.assertEqual(client.create_user.call_count, 1)
            self.assertIn("1 created, 0 refused", out.getvalue())
            out = StringIO()
            call_command("sync_lychee_users", stdout=out, stderr=err)
        self.assertIn("1 created, 1 refused", out.getvalue())
        self.assertIn("already exists?", err.getvalue())

    def test_missing_admin_credentials_are_a_command_error(self):
        with self.settings(LYCHEE_URL=GALLERY, LYCHEE_ADMIN_USER="", LYCHEE_ADMIN_PASSWORD=""):
            with self.assertRaises(CommandError):
                call_command("sync_lychee_users")
