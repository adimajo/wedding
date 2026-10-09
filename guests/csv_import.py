import csv
import logging
import re
import unicodedata
from dataclasses import dataclass, field

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.utils import timezone

from guests.models import Event, Family, Guest, Invitation

logger = logging.getLogger(__name__)

TRUE_VALUES = {"y", "yes", "true", "1", "o", "oui", "x"}
INVITED_PREFIX = "invited_"
EXPORT_HEADERS = [
    "family",
    "first_name",
    "last_name",
    "is_child",
    "email",
    "event",
    "is_attending",
    "starter",
    "main",
    "dessert",
    "comments",
    "responded_at",
]


class CsvImportError(Exception):
    """The CSV file cannot be imported (missing columns, unknown events...)."""


@dataclass
class ImportResult:
    created: int = 0
    updated: int = 0
    skipped: int = 0
    invitations_created: int = 0
    events_created: list = field(default_factory=list)


HEADER_ALIASES = {
    "e_mail": "email",
    "mail": "email",
    "courriel": "email",
    "prenom": "first_name",
    "nom": "last_name",
    "famille": "family",
    "enfant": "is_child",
}


def _header_key(name):
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode()
    key = re.sub(r"[^a-z0-9]+", "_", ascii_name.strip().lower()).strip("_")
    return HEADER_ALIASES.get(key, key)


def _is_true(value):
    return (value or "").strip().lower() in TRUE_VALUES


def import_guests(path, dry_run=False, create_events=False):
    """Import guests (and their invitations) from a CSV file.

    The first row names the columns (case and punctuation do not matter): ``first_name`` is required;
    ``last_name``, ``family``, ``is_child`` and ``email`` are optional (French and "First Name"-style
    headers are understood too); every ``invited_<event-slug>`` column
    (``y`` / ``n``) invites the guest to that event. Extra columns are ignored.

    Guests are matched on their e-mail address (case-insensitive) or, without e-mail, on family and name, so
    running the import again updates instead of duplicating, and never removes anything. Nothing is written
    when ``dry_run`` is true. Returns an :class:`ImportResult`.
    """
    result = ImportResult()
    with transaction.atomic():
        with open(path, newline="", encoding="utf-8-sig") as csvfile:
            reader = csv.reader(csvfile)
            headers = [_header_key(cell) for cell in next(reader, [])]
            if "first_name" not in headers:
                raise CsvImportError("The first row must contain a 'first_name' column")
            index = {name: position for position, name in enumerate(headers) if name}
            events = _resolve_events(index, create_events, result)
            for line_number, row in enumerate(reader, start=2):
                if not any(cell.strip() for cell in row):
                    continue
                _import_row(row, index, events, line_number, result)
        if dry_run:
            transaction.set_rollback(True)
    return result


def _resolve_events(index, create_events, result):
    events = {}
    missing = []
    for name in index:
        if not name.startswith(INVITED_PREFIX):
            continue
        slug = name[len(INVITED_PREFIX) :].replace("_", "-")
        event = (
            Event.objects.filter(slug=slug).first() or Event.objects.filter(slug=name[len(INVITED_PREFIX) :]).first()
        )
        if event is None and create_events:
            event = Event.objects.create(slug=slug, name=slug.replace("-", " ").title())
            result.events_created.append(slug)
        if event is None:
            missing.append(slug)
        else:
            events[name] = event
    if missing:
        raise CsvImportError(
            f"Unknown event(s): {', '.join(missing)}. Create them in the admin first, or use --create-events."
        )
    return events


def _cell(row, index, name):
    position = index.get(name)
    return row[position].strip() if position is not None and position < len(row) else ""


def _import_row(row, index, events, line_number, result):
    first_name = _cell(row, index, "first_name")
    last_name = _cell(row, index, "last_name")
    if not first_name:
        logger.warning("Line %d skipped: no first name", line_number)
        result.skipped += 1
        return
    email = _cell(row, index, "email").lower()
    if email:
        try:
            validate_email(email)
        except ValidationError:
            logger.warning("Line %d skipped: invalid e-mail %r", line_number, email)
            result.skipped += 1
            return
    family_name = _cell(row, index, "family") or f"{first_name} {last_name}".strip()
    family = Family.objects.get_or_create(name=family_name)[0]
    is_child = _is_true(_cell(row, index, "is_child"))

    if email:
        guest = Guest.objects.filter(email__iexact=email).first()
    else:
        guest = Guest.objects.filter(email=None, family=family, first_name=first_name, last_name=last_name).first()
    if guest is None:
        guest = Guest.objects.create_user(
            first_name=first_name, last_name=last_name, email=email or None, family=family, is_child=is_child
        )
        result.created += 1
    else:
        guest.first_name, guest.last_name, guest.family, guest.is_child = first_name, last_name, family, is_child
        guest.save()
        result.updated += 1

    for column, event in events.items():
        if _is_true(_cell(row, index, column)):
            _, created = Invitation.objects.get_or_create(guest=guest, event=event)
            result.invitations_created += created


def write_export(writer):
    """Write one row per invitation (with the RSVP state) to a ``csv.writer``."""
    writer.writerow(EXPORT_HEADERS)
    invitations = Invitation.objects.select_related(
        "guest", "guest__family", "event", "meal_starter", "meal_main", "meal_dessert"
    ).order_by("event__order", "guest__family__name", "guest__first_name")
    for invitation in invitations:
        guest = invitation.guest
        writer.writerow(
            [
                guest.family.name if guest.family else "",
                guest.first_name,
                guest.last_name,
                "y" if guest.is_child else "n",
                guest.email or "",
                invitation.event.slug,
                {True: "y", False: "n", None: ""}[invitation.is_attending],
                invitation.meal_starter.label if invitation.meal_starter else "",
                invitation.meal_main.label if invitation.meal_main else "",
                invitation.meal_dessert.label if invitation.meal_dessert else "",
                invitation.comments,
                timezone.localtime(invitation.responded_at).isoformat() if invitation.responded_at else "",
            ]
        )
