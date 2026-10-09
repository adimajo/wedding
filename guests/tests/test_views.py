import csv
import io
from unittest import mock

from django.contrib.auth import get_user_model
from django.core import mail
from django.test import override_settings
from django.urls import reverse

from bigday.test_utils import AppTestCase
from guests import lychee
from guests.models import Guest
from guests.tests.helpers import make_event, make_family


class BaseViewsTest(AppTestCase):
    def setUp(self):
        self.ceremony = make_event(menu=True, location="Mairie", description="Rendez-vous à la mairie.")
        self.party = make_event("party", "Fête", order=1)
        self.ned, self.cat = make_family(
            self.ceremony, ("Ned", "Stark", "ned@winterfell.example"), ("Cat", "Stark", "cat@winterfell.example")
        )
        (self.tyrion,) = make_family(self.party, ("Tyrion", "Lannister", "t@casterly.example"), family="Lannisters")
        self.staff = get_user_model().objects.create_superuser("Root", "Admin", "root@example.org", "s3cret-pass-word")


class HomeTest(BaseViewsTest):
    def test_home_requires_login(self):
        response = self.client.get(reverse("home"))
        self.assertRedirects(response, f"{reverse('login')}?next=/", fetch_redirect_response=False)

    def test_home_shows_only_the_events_of_the_guest(self):
        self.client.force_login(self.ned.guest)
        response = self.client.get(reverse("home"))
        self.assertContains(response, "Cérémonie")
        self.assertContains(response, "Rendez-vous à la mairie.")
        self.assertNotContains(response, "Fête")
        self.client.force_login(self.tyrion.guest)
        self.assertContains(self.client.get(reverse("home")), "Fête")

    def test_guest_without_invitation_sees_the_welcome_only(self):
        self.client.force_login(Guest.objects.create_user("Bronn", "", "bronn@example.org"))
        response = self.client.get(reverse("home"))
        self.assertContains(response, "Bienvenue")
        self.assertNotContains(response, "Cérémonie")

    def test_photos_card_only_when_the_gallery_is_configured(self):
        self.client.force_login(self.ned.guest)
        self.assertNotContains(self.client.get(reverse("home")), reverse("photos"))
        with self.settings(LYCHEE_URL="https://wedding.example.org/photos"):
            self.assertContains(self.client.get(reverse("home")), reverse("photos"))

    def test_event_page_can_be_overridden_by_slug(self):
        with mock.patch("guests.templatetags.wedding.select_template") as select:
            select.return_value.render.return_value = "<p>custom</p>"
            self.client.force_login(self.ned.guest)
            self.client.get(reverse("home"))
        select.assert_called_with(["partials/event_ceremony.html", "partials/event.html"])


class MagicLinkTest(BaseViewsTest):
    def test_link_logs_in_and_redirects_home(self):
        response = self.client.get(reverse("magic_home", args=[self.ned.token]))
        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)
        self.assertEqual(self.client.session["_auth_user_id"], str(self.ned.guest.pk))

    def test_opening_is_recorded_for_the_named_campaign_only(self):
        self.client.get(reverse("magic_home", args=[self.ned.token]) + "?c=thank_you")
        self.ned.refresh_from_db()
        self.assertIsNotNone(self.ned.thank_you_opened)
        self.assertIsNone(self.ned.preparation_opened)

    def test_first_opening_time_is_kept(self):
        url = reverse("magic_home", args=[self.ned.token]) + "?c=preparation"
        self.client.get(url)
        self.ned.refresh_from_db()
        first = self.ned.preparation_opened
        self.client.get(url)
        self.ned.refresh_from_db()
        self.assertEqual(self.ned.preparation_opened, first)

    def test_unknown_campaign_is_ignored(self):
        response = self.client.get(reverse("magic_home", args=[self.ned.token]) + "?c=nope")
        self.assertEqual(response.status_code, 302)

    def test_unknown_token_does_not_log_in(self):
        response = self.client.get(reverse("magic_home", args=["0" * 32]))
        self.assertEqual(response.status_code, 404)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_guest_id_is_not_a_valid_token(self):
        self.assertEqual(self.client.get(reverse("magic_home", args=[str(self.ned.guest.pk)])).status_code, 404)

    def test_photos_link_logs_in_then_goes_to_the_gallery(self):
        response = self.client.get(reverse("photos_link", args=[self.ned.token]))
        self.assertRedirects(response, reverse("photos"), fetch_redirect_response=False)
        self.assertIn("_auth_user_id", self.client.session)


class StaffOnlyTest(BaseViewsTest):
    URLS = [
        ("dashboard", []),
        ("export_guests", []),
        ("campaign_preview", ["invitation", "ceremony"]),
    ]

    def test_anonymous_users_are_sent_to_the_login(self):
        for name, args in self.URLS:
            with self.subTest(name):
                self.assertEqual(self.client.get(reverse(name, args=args)).status_code, 302)

    def test_ordinary_guests_are_refused(self):
        self.client.force_login(self.ned.guest)
        for name, args in self.URLS:
            with self.subTest(name):
                response = self.client.get(reverse(name, args=args))
                self.assertEqual(response.status_code, 302)
                self.assertIn("/admin/login/", response["Location"])
        response = self.client.post(reverse("campaign_test", args=["invitation", "ceremony"]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(len(mail.outbox), 0)

    def test_guest_list_is_not_public(self):
        self.assertEqual(self.client.get("/guests/").status_code, 404)

    def test_staff_can_see_the_dashboard_and_previews(self):
        self.client.force_login(self.staff)
        self.assertContains(self.client.get(reverse("dashboard")), "Cérémonie")
        self.assertContains(self.client.get(reverse("campaign_preview", args=["invitation", "ceremony"])), "Répondre")

    def test_test_send_goes_to_the_staff_member_only(self):
        self.client.force_login(self.staff)
        self.client.post(reverse("campaign_test", args=["invitation", "ceremony"]))
        (message,) = mail.outbox
        self.assertEqual(message.to, ["root@example.org"])
        self.assertEqual(message.cc, [])

    def test_test_send_is_post_only(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse("campaign_test", args=["invitation", "ceremony"])).status_code, 405)

    def test_unknown_campaign_or_event_is_404(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.client.get(reverse("campaign_preview", args=["nope", "ceremony"])).status_code, 404)
        self.assertEqual(self.client.get(reverse("campaign_preview", args=["invitation", "nope"])).status_code, 404)

    def test_dashboard_counts(self):
        self.ned.is_attending = True
        self.ned.save()
        self.cat.is_attending = False
        self.cat.save()
        self.client.force_login(self.staff)
        item = self.client.get(reverse("dashboard")).context["events"][0]
        self.assertEqual((item["total"], item["attending"], item["declined"], item["pending"]), (2, 1, 1, 0))
        self.assertEqual([invitation.guest.first_name for invitation in item["without_meal"]], ["Ned"])

    def test_export_contains_the_answers(self):
        self.ned.is_attending = True
        self.ned.comments = "Hello"
        self.ned.save()
        self.client.force_login(self.staff)
        response = self.client.get(reverse("export_guests"))
        rows = list(csv.DictReader(io.StringIO(response.content.decode())))
        ned = next(row for row in rows if row["first_name"] == "Ned")
        self.assertEqual((ned["event"], ned["is_attending"], ned["comments"]), ("ceremony", "y", "Hello"))


class RegistrationTest(AppTestCase):
    DATA = {
        "first_name": "Bran",
        "last_name": "Stark",
        "email": "bran@winterfell.example",
        "password1": "a-long-enough-pass-1",
        "password2": "a-long-enough-pass-1",
        "registration_code": "sesame",
    }

    def test_registration_needs_the_code(self):
        response = self.client.post(reverse("register"), {**self.DATA, "registration_code": "wrong"})
        self.assertContains(response, "Code d&#x27;accès incorrect.")
        self.assertFalse(Guest.objects.exists())

    def test_registration_with_the_code_logs_in(self):
        response = self.client.post(reverse("register"), self.DATA)
        self.assertRedirects(response, reverse("home"), fetch_redirect_response=False)
        self.assertEqual(Guest.objects.get().email, "bran@winterfell.example")

    @override_settings(REGISTRATION_CODE="")
    def test_registration_can_be_disabled(self):
        self.assertEqual(self.client.get(reverse("register")).status_code, 404)

    def test_password_reset_works_for_guests_without_password(self):
        Guest.objects.create_user("Ned", "Stark", "ned@winterfell.example")
        self.client.post(reverse("password_reset"), {"email": "NED@winterfell.example"})
        (message,) = mail.outbox
        self.assertIn("https://wedding.example.org/password/reset/", message.body)


class HealthTest(AppTestCase):
    def test_healthz(self):
        response = self.client.get(reverse("healthz"))
        self.assertEqual((response.status_code, response.content), (200, b"ok"))


class PhotosTest(BaseViewsTest):
    def test_disabled_without_gallery(self):
        self.client.force_login(self.ned.guest)
        self.assertEqual(self.client.get(reverse("photos")).status_code, 404)

    def test_requires_login(self):
        with self.settings(LYCHEE_URL="https://wedding.example.org/photos"):
            self.assertEqual(self.client.get(reverse("photos")).status_code, 302)

    def test_redirects_to_the_gallery_with_its_cookies(self):
        self.client.force_login(self.ned.guest)
        with (
            self.settings(LYCHEE_URL="https://wedding.example.org/photos"),
            mock.patch.object(lychee, "login_guest", return_value={"lychee_session": "abc", "XSRF-TOKEN": "xyz"}),
        ):
            response = self.client.get(reverse("photos"))
        self.assertRedirects(response, "https://wedding.example.org/photos/", fetch_redirect_response=False)
        self.assertEqual(response.cookies["lychee_session"].value, "abc")
        self.assertTrue(response.cookies["lychee_session"]["httponly"])
        self.assertEqual(response.cookies["XSRF-TOKEN"].value, "xyz")

    def test_gallery_failure_is_reported_nicely(self):
        self.client.force_login(self.ned.guest)
        with (
            self.settings(LYCHEE_URL="https://wedding.example.org/photos"),
            mock.patch.object(lychee, "login_guest", side_effect=lychee.LycheeError("down")),
        ):
            response = self.client.get(reverse("photos"), follow=True)
        self.assertContains(response, "momentanément indisponible")
