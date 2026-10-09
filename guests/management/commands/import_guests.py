from django.core.management import BaseCommand, CommandError

from guests import csv_import


class Command(BaseCommand):
    help = (
        "Import guests from a CSV file: first_name (required), last_name, family, is_child, email and one "
        "invited_<event-slug> column (y/n) per event."
    )

    def add_arguments(self, parser):
        parser.add_argument("filename", type=str)
        parser.add_argument("--dry-run", action="store_true", help="Only report what would change")
        parser.add_argument("--create-events", action="store_true", help="Create the events named by the columns")

    def handle(self, filename, *args, dry_run=False, create_events=False, **options):
        try:
            result = csv_import.import_guests(filename, dry_run=dry_run, create_events=create_events)
        except csv_import.CsvImportError as exc:
            raise CommandError(str(exc)) from exc
        prefix = "[dry-run] " if dry_run else ""
        self.stdout.write(
            f"{prefix}{result.created} created, {result.updated} already present, {result.skipped} skipped, "
            f"{result.invitations_created} invitations created"
        )
