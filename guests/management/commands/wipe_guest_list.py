from django.core.management import BaseCommand

from guests.models import Family, Guest


class Command(BaseCommand):
    help = "Delete every guest (staff accounts are kept) together with their invitations and answers."

    def add_arguments(self, parser):
        parser.add_argument("--yes", action="store_true", help="Do not ask for confirmation")

    def handle(self, *args, yes, **options):
        queryset = Guest.objects.filter(is_staff=False, is_superuser=False)
        count = queryset.count()
        if not yes and input(f"Really delete all {count} guests? (y/n) ") != "y":
            self.stdout.write("Cancelled")
            return
        queryset.delete()
        Family.objects.filter(guest=None).delete()
        self.stdout.write(f"{count} guests deleted")
