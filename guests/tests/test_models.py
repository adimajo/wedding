from django.db import IntegrityError, transaction

from bigday.test_utils import AppTestCase
from guests.models import Guest, Invitation
from guests.tests.helpers import make_event, make_family


class ModelTest(AppTestCase):
    def test_several_guests_without_email_are_allowed(self):
        Guest.objects.create_user("Arya", "Stark", "")
        Guest.objects.create_user("Bran", "Stark", None)
        self.assertEqual(Guest.objects.filter(email=None).count(), 2)

    def test_emails_are_unique(self):
        Guest.objects.create_user("Ned", "Stark", "ned@winterfell.example")
        with self.assertRaises(IntegrityError), transaction.atomic():
            Guest.objects.create_user("Eddard", "Stark", "ned@winterfell.example")

    def test_guests_have_no_usable_password_by_default(self):
        guest = Guest.objects.create_user("Ned", "Stark", "ned@winterfell.example")
        self.assertFalse(guest.has_usable_password())

    def test_tokens_are_unique_random_and_long(self):
        event = make_event()
        first, second = make_family(
            event, ("Ned", "Stark", "ned@winterfell.example"), ("Cat", "Stark", "cat@w.example")
        )
        self.assertNotEqual(first.token, second.token)
        self.assertEqual(len(first.token), 32)

    def test_one_invitation_per_guest_and_event(self):
        event = make_event()
        (invitation,) = make_family(event, ("Ned", "Stark", "ned@winterfell.example"))
        with self.assertRaises(IntegrityError), transaction.atomic():
            Invitation.objects.create(guest=invitation.guest, event=event)

    def test_family_invitations_are_scoped_to_family_and_event(self):
        ceremony, party = make_event(), make_event("party", "Fête")
        ned, cat = make_family(ceremony, ("Ned", "Stark", "ned@winterfell.example"), ("Cat", "Stark", "cat@w.example"))
        Invitation.objects.create(guest=ned.guest, event=party)
        (tyrion,) = make_family(ceremony, ("Tyrion", "Lannister", "t@c.example"), family="The Lannisters")
        self.assertEqual(set(ned.family_invitations()), {ned, cat})
        self.assertEqual(list(tyrion.family_invitations()), [tyrion])

    def test_family_invitations_without_family_is_the_guest_alone(self):
        event = make_event()
        guest = Guest.objects.create_user("Solo", "Guest", "solo@example.org")
        invitation = Invitation.objects.create(guest=guest, event=event)
        self.assertEqual(list(invitation.family_invitations()), [invitation])

    def test_superuser_needs_an_email(self):
        with self.assertRaises(ValueError):
            Guest.objects.create_superuser("Root", "Admin", "", "x" * 20)
