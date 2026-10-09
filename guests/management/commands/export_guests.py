import csv

from django.core.management import BaseCommand

from guests import csv_import


class Command(BaseCommand):
    help = "Write the invitations with their RSVP state as CSV on the standard output."

    def handle(self, *args, **options):
        csv_import.write_export(csv.writer(self.stdout, lineterminator="\n"))
