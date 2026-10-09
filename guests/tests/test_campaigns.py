import tempfile
from io import StringIO
from pathlib import Path
from unittest import mock

from django.core import mail
from django.core.management import CommandError, call_command
from django.template import Context, Template
from django.test import override_settings

from bigday.test_utils import AppTestCase
from guests.campaigns import CAMPAIGNS, INVITATION, PREPARATION, THANK_YOU
from guests.tests.helpers import make_event, make_family

PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7\x9a\xa0\xa0\x00\x00\x00\x00IEND\xaeB`\x82"
)


class CampaignTest(AppTestCase):
    def setUp(self):
        self.event = make_event(location="Mairie")
        self.other_event = make_event("party", "Fête")
        self.ned, self.cat, self.arya = make_family(
            self.event,
            ("Ned", "Stark", "ned@winterfell.example"),
            ("Cat", "Stark", "cat@winterfell.example"),
            ("Arya", "Stark", None, True),
        )
        (self.tyrion,) = make_family(self.other_event, ("Tyrion", "Lannister", "t@c.example"), family="Lannisters")

    def run_command(self, *args):
        out = StringIO()
        call_command("send_campaign", *args, "--delay", "0", stdout=out)
        return out.getvalue()

    def test_dry_run_sends_and_marks_nothing(self):
        output = self.run_command("invitation", "--event", "ceremony")
        self.assertEqual(len(mail.outbox), 0)
        self.assertIn("would send to ned@winterfell.example", output)
        self.ned.refresh_from_db()
        self.assertIsNone(self.ned.invitation_sent)

    def test_send_only_reaches_guests_with_an_email_of_that_event(self):
        self.run_command("invitation", "--event", "ceremony", "--send")
        self.assertEqual(sorted(m.to[0] for m in mail.outbox), ["cat@winterfell.example", "ned@winterfell.example"])

    def test_mark_sent_makes_the_campaign_idempotent(self):
        self.run_command("invitation", "--event", "ceremony", "--send", "--mark-sent")
        self.run_command("invitation", "--event", "ceremony", "--send", "--mark-sent")
        self.assertEqual(len(mail.outbox), 2)
        self.ned.refresh_from_db()
        self.assertIsNotNone(self.ned.invitation_sent)
        self.assertIsNone(self.ned.save_the_date_sent)

    def test_send_without_mark_sent_does_not_remember(self):
        self.run_command("invitation", "--event", "ceremony", "--send")
        self.ned.refresh_from_db()
        self.assertIsNone(self.ned.invitation_sent)

    def test_reset_forgets_who_received_it(self):
        self.run_command("invitation", "--event", "ceremony", "--send", "--mark-sent")
        mail.outbox.clear()
        self.run_command("invitation", "--event", "ceremony", "--reset", "--send")
        self.assertEqual(len(mail.outbox), 2)

    def test_mark_sent_requires_send(self):
        with self.assertRaises(CommandError):
            self.run_command("invitation", "--event", "ceremony", "--mark-sent")

    def test_event_is_required_when_there_are_several(self):
        with self.assertRaisesMessage(CommandError, "ceremony, party"):
            self.run_command("invitation")
        with self.assertRaises(CommandError):
            self.run_command("invitation", "--event", "nope")

    def test_event_is_optional_when_there_is_only_one(self):
        self.other_event.delete()
        self.assertIn("would send", self.run_command("invitation"))

    def test_preparation_and_thank_you_only_reach_attending_guests(self):
        self.ned.is_attending = True
        self.ned.save()
        self.cat.is_attending = False
        self.cat.save()
        for key in ("preparation", "thank_you"):
            mail.outbox.clear()
            self.run_command(key, "--event", "ceremony", "--send")
            self.assertEqual([m.to for m in mail.outbox], [["ned@winterfell.example"]])
        self.assertTrue(PREPARATION.attending_only and THANK_YOU.attending_only)
        self.assertFalse(INVITATION.attending_only)

    def test_inactive_guests_are_skipped(self):
        self.cat.guest.is_active = False
        self.cat.guest.save()
        self.run_command("invitation", "--event", "ceremony", "--send")
        self.assertEqual([m.to for m in mail.outbox], [["ned@winterfell.example"]])

    def test_a_failure_does_not_stop_the_others_nor_mark_the_failed_one(self):
        real_send = mail.EmailMultiAlternatives.send
        calls = []

        def flaky(message, *args, **kwargs):
            calls.append(message.to[0])
            if message.to[0] == "cat@winterfell.example":
                raise OSError("smtp down")
            return real_send(message, *args, **kwargs)

        with (
            mock.patch.object(mail.EmailMultiAlternatives, "send", flaky),
            self.assertLogs("guests.campaigns", level="ERROR"),
            self.assertRaisesMessage(CommandError, "1 e-mails could not be sent"),
        ):
            self.run_command("invitation", "--event", "ceremony", "--send", "--mark-sent")
        self.assertEqual(sorted(calls), ["cat@winterfell.example", "ned@winterfell.example"])
        self.ned.refresh_from_db()
        self.cat.refresh_from_db()
        self.assertIsNotNone(self.ned.invitation_sent)
        self.assertIsNone(self.cat.invitation_sent)

    def test_message_headers_and_links(self):
        self.run_command("invitation", "--event", "ceremony", "--send")
        message = next(m for m in mail.outbox if m.to == ["ned@winterfell.example"])
        self.assertEqual(message.subject, "Invitation - Cérémonie")
        self.assertEqual(message.from_email, "Alex & Sam <alex@example.org>")
        self.assertEqual(message.cc, ["cc@example.org"])
        self.assertEqual(message.reply_to, ["contact@example.org"])
        html = message.alternatives[0][0]
        self.assertIn(f"https://wedding.example.org/invite/{self.ned.token}/", html)
        self.assertIn(f"https://wedding.example.org/home/{self.ned.token}/?c=invitation", html)
        self.assertNotIn(self.cat.token, html)
        self.assertIn(f"https://wedding.example.org/invite/{self.ned.token}/", message.body)

    @override_settings(INVITATION_SUBJECT="Mariage ({event}) {unknown}")
    def test_subject_placeholder_is_replaced_without_str_format(self):
        self.assertEqual(INVITATION.subject(self.event), "Mariage (Cérémonie) {unknown}")

    def test_links_in_the_thank_you_mail_include_photos_only_with_a_gallery(self):
        self.ned.is_attending = True
        self.ned.save()
        self.run_command("thank_you", "--event", "ceremony", "--send")
        self.assertNotIn("/photos/", mail.outbox[0].alternatives[0][0])
        mail.outbox.clear()
        with self.settings(LYCHEE_URL="https://wedding.example.org/photos"):
            self.run_command("thank_you", "--event", "ceremony", "--send")
        self.assertIn(f"/photos/{self.ned.token}/", mail.outbox[0].alternatives[0][0])

    def test_every_campaign_renders_a_preview_and_a_message(self):
        for campaign in CAMPAIGNS.values():
            with self.subTest(campaign.key):
                self.assertIn("Cérémonie", campaign.render_preview(self.event))
                self.assertIn("Cérémonie", campaign.build_message(self.ned).alternatives[0][0])

    def test_preview_uses_dead_links(self):
        html = INVITATION.render_preview(self.event)
        self.assertIn("/invite/" + "0" * 32 + "/", html)
        self.assertNotIn("cid:", html)


class InlineImageTest(AppTestCase):
    def setUp(self):
        self.static_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.static_dir.cleanup)
        image = Path(self.static_dir.name) / "hero.png"
        image.write_bytes(PNG)
        (Path(self.static_dir.name) / "icon.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>")
        self.event = make_event()
        (self.ned,) = make_family(self.event, ("Ned", "Stark", "ned@winterfell.example"))

    def settings_with_images(self, **extra):
        values = {"STATICFILES_DIRS": [self.static_dir.name], "EMAIL_HERO_IMAGE": "hero.png"}
        values.update(EMAIL_HEADER_IMAGE="icon.svg", **extra)
        return override_settings(**values)

    def test_configured_images_are_embedded_with_matching_content_ids(self):
        with self.settings_with_images():
            message = INVITATION.build_message(self.ned)
        html = message.alternatives[0][0]
        self.assertIn('src="cid:hero.png"', html)
        self.assertIn('src="cid:icon.svg"', html)
        attachments = {a.get("Content-ID"): a.get_content_type() for a in message.attachments}
        self.assertEqual(attachments, {"<hero.png>": "image/png", "<icon.svg>": "image/svg+xml"})

    def test_previews_use_static_urls(self):
        with self.settings_with_images():
            html = INVITATION.render_preview(self.event)
        self.assertIn('src="/static/hero.png"', html)

    def test_missing_image_is_logged_and_skipped(self):
        with self.settings_with_images(EMAIL_HERO_IMAGE="absent.png"), self.assertLogs("guests.campaigns", "WARNING"):
            message = INVITATION.build_message(self.ned)
        self.assertEqual(len(message.attachments), 1)

    def test_email_image_tag_registers_each_image_once(self):
        template = Template("{% load wedding %}{% email_image 'a/b c.png' %}{% email_image 'a/b c.png' %}")
        images = []
        rendered = template.render(Context({"email_mode": True, "inline_images": images}))
        self.assertEqual(rendered, "cid:a_b_c.pngcid:a_b_c.png")
        self.assertEqual(images, ["a/b c.png"])
