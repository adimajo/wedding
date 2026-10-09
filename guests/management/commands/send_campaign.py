from django.core.management import BaseCommand, CommandError

from guests.campaigns import CAMPAIGNS
from guests.models import Event


class Command(BaseCommand):
    help = (
        "Send an e-mail campaign to the guests of an event who have not received it yet. "
        "Without --send nothing is sent (dry run)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "campaign", choices=sorted(CAMPAIGNS), help="save_the_date, invitation, preparation or thank_you"
        )
        parser.add_argument("--event", help="Slug of the event (optional when there is only one)")
        parser.add_argument("--send", action="store_true", help="Actually send the e-mails")
        parser.add_argument("--mark-sent", action="store_true", help="Remember who received it (requires --send)")
        parser.add_argument("--reset", action="store_true", help="Forget who already received this campaign")
        parser.add_argument("--delay", type=float, default=1.0, help="Seconds to wait between e-mails")

    def handle(self, *args, campaign, event, send, mark_sent, reset, delay, **options):
        if mark_sent and not send:
            raise CommandError("--mark-sent only makes sense together with --send")
        event_object = self._event(event)
        selected = CAMPAIGNS[campaign]
        if reset:
            self.stdout.write(f"Reset {selected.reset_sent(event_object)} invitations")
        sent, failed = selected.send_all(event_object, send=send, mark_sent=mark_sent, delay=delay, stdout=self.stdout)
        if send:
            self.stdout.write(f"{sent} sent, {failed} failed")
        if failed:
            raise CommandError(f"{failed} e-mails could not be sent")

    @staticmethod
    def _event(slug):
        events = Event.objects.all()
        if slug:
            try:
                return events.get(slug=slug)
            except Event.DoesNotExist:
                raise CommandError(f"Unknown event {slug!r}") from None
        if events.count() == 1:
            return events.get()
        raise CommandError("Several events exist: choose one with --event (" + ", ".join(e.slug for e in events) + ")")
