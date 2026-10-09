import csv
from pathlib import Path

import qrcode
import qrcode.image.svg
from django.conf import settings
from django.core.management import BaseCommand, CommandError
from django.urls import reverse

from guests import lychee
from guests.models import Event, Invitation


class Command(BaseCommand):
    help = (
        "Write one SVG QR code per invitation (for table cards, programmes...) plus an index.csv mapping the "
        "files to the guests. Files are named after the guest id, not the name."
    )

    def add_arguments(self, parser):
        parser.add_argument("output_dir", type=Path)
        parser.add_argument("--event", help="Slug of the event (default: all)")
        parser.add_argument(
            "--target",
            choices=["home", "photos"],
            help="Where the code leads (default: the photo gallery when configured, else the site)",
        )

    def handle(self, *args, output_dir, event, target, **options):
        target = target or ("photos" if lychee.is_enabled() else "home")
        if target == "photos" and not lychee.is_enabled():
            raise CommandError("LYCHEE_URL is not configured")
        invitations = Invitation.objects.select_related("guest", "event").order_by("event__order", "guest__pk")
        if event:
            if not Event.objects.filter(slug=event).exists():
                raise CommandError(f"Unknown event {event!r}")
            invitations = invitations.filter(event__slug=event)
        output_dir.mkdir(parents=True, exist_ok=True)
        route = "photos_link" if target == "photos" else "magic_home"
        with open(output_dir / "index.csv", "w", newline="", encoding="utf-8") as index:
            writer = csv.writer(index)
            writer.writerow(["file", "first_name", "last_name", "event"])
            for invitation in invitations:
                url = f"{settings.SITE_URL}{reverse(route, args=[invitation.token])}"
                filename = f"guest-{invitation.guest.pk}-{invitation.event.slug}.svg"
                qrcode.make(url, image_factory=qrcode.image.svg.SvgPathImage).save(str(output_dir / filename))
                writer.writerow(
                    [filename, invitation.guest.first_name, invitation.guest.last_name, invitation.event.slug]
                )
        self.stdout.write(f"{invitations.count()} QR codes written to {output_dir}")
