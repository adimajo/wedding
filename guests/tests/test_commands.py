import csv
import io
import tempfile
from datetime import timedelta
from io import StringIO
from pathlib import Path
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import CommandError, call_command
from django.utils import timezone

from bigday.test_utils import AppTestCase
from guests.models import Event, Family, Guest, Invitation
from guests.tests.helpers import make_event, make_family

CSV = Path(__file__).parent / "data" / "guests-test.csv"


class ImportExportTest(AppTestCase):
    def setUp(self):
        make_event("ceremony", "Cérémonie")
        make_event("party", "Fête")

    def run_import(self, *args):
        out = StringIO()
        with self.assertLogs("guests.csv_import", level="WARNING") as logs:
            call_command("import_guests", str(CSV), *args, stdout=out)
        return out.getvalue(), logs.output

    def test_import_creates_guests_families_and_invitations(self):
        output, warnings = self.run_import()
        self.assertIn("4 created, 0 already present, 1 skipped, 6 invitations created", output)
        self.assertTrue(any("invalid e-mail" in line for line in warnings))
        self.assertEqual(Family.objects.count(), 2)
        self.assertEqual(Guest.objects.filter(family__name="The Starks").count(), 3)
        arya = Guest.objects.get(first_name="Arya")
        self.assertTrue(arya.is_child)
        self.assertIsNone(arya.email)
        self.assertEqual(sorted(arya.invitations.values_list("event__slug", flat=True)), ["ceremony"])
        self.assertEqual(Guest.objects.get(first_name="Catelyn").email, "CATELYN@winterfell.example".lower())

    def test_import_is_idempotent_and_never_deletes(self):
        self.run_import()
        Invitation.objects.filter(guest__first_name="Arya").delete()
        output, _ = self.run_import()
        self.assertIn("0 created, 4 already present", output)
        self.assertEqual(Guest.objects.count(), 4)
        self.assertEqual(Invitation.objects.count(), 6)  # Arya's came back, nothing was removed

    def test_import_updates_names_matched_by_email_case_insensitively(self):
        Guest.objects.create_user("Cate", "S", "catelyn@winterfell.example")
        self.run_import()
        self.assertEqual(Guest.objects.get(email="catelyn@winterfell.example").first_name, "Catelyn")

    def test_dry_run_changes_nothing(self):
        output, _ = self.run_import("--dry-run")
        self.assertIn("[dry-run] 4 created", output)
        self.assertFalse(Guest.objects.exists())
        self.assertFalse(Family.objects.exists())

    def test_unknown_event_column_is_an_error_unless_created(self):
        Event.objects.filter(slug="party").delete()
        with self.assertRaisesMessage(CommandError, "Unknown event(s): party"):
            self.run_import()
        self.assertFalse(Guest.objects.exists())
        self.run_import("--create-events")
        self.assertTrue(Event.objects.filter(slug="party", name="Party").exists())

    def test_french_headers_are_understood(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8-sig") as french:
            french.write(
                "Famille,Prénom,Nom,Enfant,Courriel,invited_party\nDupont,Zoé,Dupont,oui,zoe@example.org,oui\n"
            )
        self.addCleanup(Path(french.name).unlink)
        call_command("import_guests", french.name, stdout=StringIO())
        zoe = Guest.objects.get(email="zoe@example.org")
        self.assertEqual((zoe.family.name, zoe.last_name, zoe.is_child), ("Dupont", "Dupont", True))
        self.assertEqual(zoe.invitations.get().event.slug, "party")

    def test_first_name_column_is_required(self):
        with tempfile.NamedTemporaryFile("w", suffix=".csv", delete=False, encoding="utf-8") as bad:
            bad.write("nom,email\nStark,ned@x.example\n")
        self.addCleanup(Path(bad.name).unlink)
        with self.assertRaisesMessage(CommandError, "first_name"):
            call_command("import_guests", bad.name)

    def test_export_round_trip_columns(self):
        self.run_import()
        invitation = Invitation.objects.get(guest__first_name="Ned", event__slug="ceremony")
        invitation.is_attending = False
        invitation.save()
        out = StringIO()
        call_command("export_guests", stdout=out)
        rows = list(csv.DictReader(io.StringIO(out.getvalue())))
        self.assertEqual(len(rows), 6)
        ned = next(r for r in rows if r["first_name"] == "Ned" and r["event"] == "ceremony")
        self.assertEqual((ned["family"], ned["is_attending"], ned["is_child"]), ("The Starks", "n", "n"))


class MaintenanceCommandsTest(AppTestCase):
    def setUp(self):
        event = make_event()
        self.old, self.new = make_family(
            event, ("Old", "Guest", "old@example.org"), ("New", "Guest", "new@example.org"), family="Guests"
        )
        Guest.objects.filter(pk=self.old.guest.pk).update(created=timezone.now() - timedelta(days=200))
        self.admin = get_user_model().objects.create_superuser("Root", "Admin", "root@example.org", "x" * 20)
        Guest.objects.filter(pk=self.admin.pk).update(created=timezone.now() - timedelta(days=900))

    def test_purge_keeps_recent_guests_and_staff(self):
        call_command("purge_guests", "--older-than-days", "180", "--yes", stdout=StringIO())
        self.assertEqual(set(Guest.objects.values_list("email", flat=True)), {"new@example.org", "root@example.org"})

    def test_purge_asks_for_confirmation(self):
        with mock.patch("builtins.input", return_value="n"):
            call_command("purge_guests", stdout=StringIO())
        self.assertEqual(Guest.objects.count(), 3)

    def test_purge_removes_families_left_empty(self):
        call_command("purge_guests", "--older-than-days", "0", "--yes", stdout=StringIO())
        self.assertFalse(Family.objects.exists())

    def test_wipe_keeps_staff(self):
        call_command("wipe_guest_list", "--yes", stdout=StringIO())
        self.assertEqual(list(Guest.objects.values_list("email", flat=True)), ["root@example.org"])
        self.assertFalse(Invitation.objects.exists())

    def test_wipe_asks_for_confirmation(self):
        with mock.patch("builtins.input", return_value=""):
            call_command("wipe_guest_list", stdout=StringIO())
        self.assertEqual(Guest.objects.count(), 3)


class QrCodeTest(AppTestCase):
    def setUp(self):
        self.event = make_event()
        (self.ned,) = make_family(self.event, ("Ned", "Stark", "ned@winterfell.example"))
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)

    def test_files_are_named_after_ids_and_indexed(self):
        out = StringIO()
        call_command("generate_qr_codes", self.directory.name, stdout=out)
        names = sorted(path.name for path in Path(self.directory.name).iterdir())
        self.assertEqual(names, [f"guest-{self.ned.guest.pk}-ceremony.svg", "index.csv"])
        self.assertNotIn("Ned", "".join(names))
        index = (Path(self.directory.name) / "index.csv").read_text()
        self.assertIn("Ned,Stark,ceremony", index)

    def test_code_points_to_the_personal_link(self):
        with mock.patch("qrcode.make") as make:
            make.return_value.save = mock.Mock()
            call_command("generate_qr_codes", self.directory.name, stdout=StringIO())
        self.assertEqual(make.call_args.args[0], f"https://wedding.example.org/home/{self.ned.token}/")
        with self.settings(LYCHEE_URL="https://wedding.example.org/photos"), mock.patch("qrcode.make") as make:
            call_command("generate_qr_codes", self.directory.name, stdout=StringIO())
        self.assertEqual(make.call_args.args[0], f"https://wedding.example.org/photos/{self.ned.token}/")

    def test_options_are_validated(self):
        with self.assertRaisesMessage(CommandError, "LYCHEE_URL"):
            call_command("generate_qr_codes", self.directory.name, "--target", "photos")
        with self.assertRaisesMessage(CommandError, "Unknown event"):
            call_command("generate_qr_codes", self.directory.name, "--event", "nope")
