from django.urls import reverse

from bigday.test_utils import AppTestCase
from guests.models import MealOption
from guests.tests.helpers import make_event, make_family


class RsvpTest(AppTestCase):
    def setUp(self):
        self.event = make_event(menu=True)
        self.ned, self.cat, self.arya = make_family(
            self.event,
            ("Ned", "Stark", "ned@winterfell.example"),
            ("Cat", "Stark", "cat@winterfell.example"),
            ("Arya", "Stark", None, True),
        )
        self.beef = MealOption.objects.get(key="beef")
        self.veggie = MealOption.objects.get(key="veggie")
        self.cake = MealOption.objects.get(key="cake")
        self.url = reverse("rsvp", args=[self.ned.token])

    def prefix(self, invitation):
        return f"inv{invitation.pk}"

    def answer(self, invitation, attending, **meals):
        data = {f"{self.prefix(invitation)}-attending": "yes" if attending else "no"}
        for course, option in meals.items():
            data[f"{self.prefix(invitation)}-meal_{course}"] = option.pk
        return data

    def full_answer(self, **extra):
        data = {}
        data.update(self.answer(self.ned, True, main=self.beef, dessert=self.cake))
        data.update(self.answer(self.cat, False))
        data.update(self.answer(self.arya, True))
        data.update(extra)
        return data

    def test_page_lists_family_members_and_logs_the_guest_in(self):
        response = self.client.get(self.url)
        self.assertContains(response, "Ned Stark")
        self.assertContains(response, "Cat Stark")
        self.assertContains(response, "Arya Stark")
        self.assertEqual(self.client.session["_auth_user_id"], str(self.ned.guest.pk))
        self.ned.refresh_from_db()
        self.assertIsNotNone(self.ned.invitation_opened)

    def test_unknown_token_is_404(self):
        self.assertEqual(self.client.get(reverse("rsvp", args=["0" * 32])).status_code, 404)

    def test_deactivated_guest_link_is_404(self):
        self.ned.guest.is_active = False
        self.ned.guest.save()
        self.assertEqual(self.client.get(self.url).status_code, 404)

    def test_children_are_not_asked_for_a_menu(self):
        response = self.client.get(self.url)
        forms = {form.invitation.pk: form for form in response.context["forms"]}
        self.assertEqual(forms[self.arya.pk].active_courses, [])
        self.assertEqual(forms[self.ned.pk].active_courses, ["meal_main", "meal_dessert"])

    def test_valid_answer_is_saved_for_the_whole_family(self):
        response = self.client.post(self.url, self.full_answer(comments="Allergie aux noix"))
        self.assertRedirects(response, reverse("rsvp_confirm", args=[self.ned.token]))
        for invitation in (self.ned, self.cat, self.arya):
            invitation.refresh_from_db()
            self.assertIsNotNone(invitation.responded_at)
        self.assertTrue(self.ned.is_attending)
        self.assertEqual((self.ned.meal_main, self.ned.meal_dessert), (self.beef, self.cake))
        self.assertFalse(self.cat.is_attending)
        self.assertTrue(self.arya.is_attending)
        self.assertIsNone(self.arya.meal_main)
        self.assertEqual(self.ned.comments, "Allergie aux noix")

    def test_comments_are_appended(self):
        self.client.post(self.url, self.full_answer(comments="Un"))
        self.client.post(self.url, self.full_answer(comments="Deux"))
        self.ned.refresh_from_db()
        self.assertEqual(self.ned.comments, "Un; Deux")

    def test_attending_adult_must_choose_every_course(self):
        data = self.full_answer()
        del data[f"{self.prefix(self.ned)}-meal_dessert"]
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Merci de choisir un menu.")
        self.ned.refresh_from_db()
        self.assertIsNone(self.ned.is_attending)

    def test_missing_attendance_answer_is_an_error(self):
        data = self.full_answer()
        del data[f"{self.prefix(self.cat)}-attending"]
        response = self.client.post(self.url, data)
        self.assertContains(response, "Merci d&#x27;indiquer si cette personne sera présente.")

    def test_declining_clears_previous_meals(self):
        self.client.post(self.url, self.full_answer())
        data = self.full_answer()
        data.update(self.answer(self.ned, False, main=self.beef))
        self.client.post(self.url, data)
        self.ned.refresh_from_db()
        self.assertFalse(self.ned.is_attending)
        self.assertIsNone(self.ned.meal_main)

    def test_meal_of_another_event_is_rejected(self):
        other = make_event("party", "Fête", menu=True)
        foreign = MealOption.objects.filter(event=other, course="main").first()
        data = self.full_answer()
        data.update(self.answer(self.ned, True, main=foreign, dessert=self.cake))
        response = self.client.post(self.url, data)
        self.assertEqual(response.status_code, 200)
        self.ned.refresh_from_db()
        self.assertIsNone(self.ned.is_attending)

    def test_event_without_menu_only_asks_attendance(self):
        event = make_event("party", "Fête")
        (invitation,) = make_family(event, ("Tyrion", "Lannister", "t@c.example"), family="The Lannisters")
        url = reverse("rsvp", args=[invitation.token])
        self.client.post(url, {f"inv{invitation.pk}-attending": "yes"})
        invitation.refresh_from_db()
        self.assertTrue(invitation.is_attending)

    def test_confirmation_depends_on_the_answers(self):
        self.client.post(self.url, self.full_answer())
        response = self.client.get(reverse("rsvp_confirm", args=[self.ned.token]))
        self.assertContains(response, "On a hâte")
        data = {}
        for invitation in (self.ned, self.cat, self.arya):
            data.update(self.answer(invitation, False))
        self.client.post(self.url, data)
        response = self.client.get(reverse("rsvp_confirm", args=[self.ned.token]))
        self.assertContains(response, "tristes")

    def test_deadline_is_shown_when_configured(self):
        with self.settings(RSVP_DEADLINE="1er mai"):
            self.assertContains(self.client.get(self.url), "avant le 1er mai")
        self.assertNotContains(self.client.get(self.url), "avant le")
