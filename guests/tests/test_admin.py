from django.contrib.auth import get_user_model
from django.urls import reverse

from bigday.test_utils import AppTestCase
from guests.models import Guest
from guests.tests.helpers import make_event, make_family


class AdminTest(AppTestCase):
    def setUp(self):
        staff = get_user_model().objects.create_superuser("Root", "Admin", "root@example.org", "s3cret-pass-word")
        self.client.force_login(staff)
        event = make_event(menu=True)
        make_family(event, ("Ned", "Stark", "ned@winterfell.example"))

    def test_changelists_and_change_pages_render(self):
        for model in ("event", "family", "guest", "invitation"):
            with self.subTest(model):
                response = self.client.get(reverse(f"admin:guests_{model}_changelist"))
                self.assertEqual(response.status_code, 200)
        guest = Guest.objects.get(email="ned@winterfell.example")
        self.assertEqual(self.client.get(reverse("admin:guests_guest_change", args=[guest.pk])).status_code, 200)

    def test_guest_can_be_added_without_password_nor_email(self):
        response = self.client.post(
            reverse("admin:guests_guest_add"),
            {
                "first_name": "Arya",
                "last_name": "Stark",
                "email": "",
                "usable_password": "false",
                "invitations-TOTAL_FORMS": "0",
                "invitations-INITIAL_FORMS": "0",
            },
        )
        self.assertEqual(
            response.status_code, 302, getattr(response, "context", None) and response.context["adminform"].form.errors
        )
        guest = Guest.objects.get(first_name="Arya")
        self.assertIsNone(guest.email)
        self.assertFalse(guest.has_usable_password())

    def test_event_admin_edits_the_menu_inline(self):
        event = make_event("party", "Fête")
        self.assertContains(self.client.get(reverse("admin:guests_event_change", args=[event.pk])), "Entrée")
