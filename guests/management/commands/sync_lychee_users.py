from django.core.management import BaseCommand, CommandError

from guests import lychee
from guests.models import Guest


class Command(BaseCommand):
    help = (
        "Create a gallery (Lychee) account for every active guest. The user name and password are derived "
        "from the guest and SECRET_KEY, so the site can log guests in without storing anything."
    )

    def add_arguments(self, parser):
        parser.add_argument("--event", help="Only guests invited to this event (slug)")
        parser.add_argument("--dry-run", action="store_true", help="Only list the accounts that would be created")

    def handle(self, *args, event, dry_run, **options):
        if not lychee.is_enabled():
            raise CommandError("LYCHEE_URL is not configured")
        guests = Guest.objects.filter(is_active=True, is_staff=False)
        if event:
            guests = guests.filter(invitations__event__slug=event).distinct()
        try:
            client = None if dry_run else lychee.admin_client()
        except lychee.LycheeError as exc:
            raise CommandError(str(exc)) from exc
        created = failed = 0
        for guest in guests:
            username = lychee.lychee_username(guest)
            if dry_run:
                self.stdout.write(f"[dry-run] would create {username}")
                continue
            try:
                client.create_user(username, lychee.lychee_password(guest))
            except lychee.LycheeError as exc:
                self.stderr.write(f"{username}: {exc} (already exists?)")
                failed += 1
            else:
                created += 1
                self.stdout.write(f"created {username}")
        if not dry_run:
            self.stdout.write(f"{created} created, {failed} refused")
