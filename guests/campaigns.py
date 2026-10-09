"""E-mail campaigns sent to the guests of an event.

Four campaigns exist; each one keeps, per invitation, when it was sent and when its personal link was opened
(``<key>_sent`` / ``<key>_opened`` on :class:`guests.models.Invitation`):

* ``save_the_date``: announces the dates
* ``invitation``: invites to answer the RSVP (attending guests answer on the RSVP page)
* ``preparation``: practical information, only for guests who said they come
* ``thank_you``: after the event, only for guests who came

The wording lives in ``guests/email_templates/*.html`` and can be overridden from the content overlay
(``SITE_CONTENT_DIR``); images are chosen by the templates with ``{% email_image %}``.
"""

import logging
import mimetypes
import time
from dataclasses import dataclass
from email.mime.image import MIMEImage

from django.conf import settings
from django.contrib.staticfiles import finders
from django.core.mail import EmailMultiAlternatives
from django.http import Http404
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from guests import lychee
from guests.models import Guest, Invitation
from guests.templatetags.wedding import content_id

logger = logging.getLogger(__name__)

DUMMY_TOKEN = "0" * 32  # noqa: S105


@dataclass(frozen=True)
class Campaign:
    key: str
    label: str
    template: str
    subject_setting: str
    attending_only: bool = False
    main_color: str = "#ffffff"
    font_color: str = "#000000"

    @property
    def sent_field(self):
        return f"{self.key}_sent"

    @property
    def opened_field(self):
        return f"{self.key}_opened"

    def subject(self, event):
        return getattr(settings, self.subject_setting).replace("{event}", event.name)

    def pending(self, event):
        """Invitations of an event that this campaign still has to reach."""
        queryset = Invitation.objects.filter(event=event, guest__is_active=True, **{self.sent_field: None})
        queryset = queryset.exclude(guest__email=None).select_related("guest", "event")
        if self.attending_only:
            queryset = queryset.filter(is_attending=True)
        return queryset.order_by("guest__first_name", "guest__last_name", "pk")

    def mark_opened(self, invitation):
        if getattr(invitation, self.opened_field) is None:
            setattr(invitation, self.opened_field, timezone.now())
            invitation.save(update_fields=[self.opened_field])

    def build_context(self, invitation, preview=False):
        token = invitation.token
        site_url = settings.SITE_URL
        context = {
            "campaign": self.key,
            "page_title": f"{settings.SITE_TITLE} - {invitation.event.name}",
            "preheader_text": f"{settings.COUPLE_NAMES} - {invitation.event.name}",
            "main_color": self.main_color,
            "font_color": self.font_color,
            "hero_image": settings.EMAIL_HERO_IMAGE,
            "header_image": settings.EMAIL_HEADER_IMAGE,
            "couple": settings.COUPLE_NAMES,
            "site_title": settings.SITE_TITLE,
            "site_url": site_url,
            "reply_address": settings.WEDDING_REPLY_EMAIL,
            "rsvp_deadline": settings.RSVP_DEADLINE,
            "event": invitation.event,
            "invitation": invitation,
            "guest": invitation.guest,
            "first_name": invitation.guest.first_name,
            "rsvp_url": f"{site_url}{reverse('rsvp', args=[token])}",
            "home_url": f"{site_url}{reverse('magic_home', args=[token])}?c={self.key}",
            "photos_url": f"{site_url}{reverse('photos_link', args=[token])}" if lychee.is_enabled() else "",
            "email_mode": not preview,
            "inline_images": [],
        }
        return context

    def render_preview(self, event):
        """The HTML e-mail as shown in a browser, for a dummy guest (static image URLs, dead links)."""
        invitation = dummy_invitation(event)
        return render_to_string(self.template, context=self.build_context(invitation, preview=True))

    def build_message(self, invitation, to=None, cc=None):
        context = self.build_context(invitation)
        html = render_to_string(self.template, context=context)
        text = "\n\n".join(
            part
            for part in (
                f"{settings.COUPLE_NAMES} - {invitation.event.name}",
                context["rsvp_url"] if self.key == "invitation" else context["home_url"],
            )
            if part
        )
        message = EmailMultiAlternatives(
            self.subject(invitation.event),
            text,
            settings.DEFAULT_FROM_EMAIL,
            to=to or [invitation.guest.email],
            cc=settings.WEDDING_CC_LIST if cc is None else cc,
            reply_to=[settings.WEDDING_REPLY_EMAIL] if settings.WEDDING_REPLY_EMAIL else None,
        )
        message.attach_alternative(html, "text/html")
        message.mixed_subtype = "related"
        for path in context["inline_images"]:
            self._attach_image(message, path)
        return message

    @staticmethod
    def _attach_image(message, path):
        image_path = finders.find(path)
        if not image_path:
            logger.warning("E-mail image %s not found in the static files", path)
            return
        mime_type = mimetypes.guess_type(image_path)[0] or "image/png"
        with open(image_path, "rb") as image_file:
            image = MIMEImage(image_file.read(), _subtype=mime_type.split("/", 1)[1])
        image.add_header("Content-ID", f"<{content_id(path)}>")
        message.attach(image)

    def send_all(self, event, send=False, mark_sent=False, delay=0.0, stdout=None):
        """Send the campaign to every invitation of ``event`` it has not reached yet.

        Nothing is sent unless ``send`` is true. An invitation is only marked as sent after the message was
        really handed to the mail backend; a failure for one guest does not stop the others.
        Returns ``(sent, failed)``.
        """
        write = stdout.write if stdout else print
        sent = failed = 0
        for invitation in self.pending(event):
            message = self.build_message(invitation)
            if not send:
                write(f"[dry-run] {self.key}: would send to {invitation.guest.email}")
                continue
            try:
                message.send()
            except Exception:
                logger.exception("Could not send %s to %s", self.key, invitation.guest.email)
                failed += 1
                continue
            sent += 1
            write(f"{self.key}: sent to {invitation.guest.email}")
            if mark_sent:
                setattr(invitation, self.sent_field, timezone.now())
                invitation.save(update_fields=[self.sent_field])
            if delay:
                time.sleep(delay)
        return sent, failed

    def reset_sent(self, event):
        return (
            Invitation.objects.filter(event=event).exclude(**{self.sent_field: None}).update(**{self.sent_field: None})
        )


def dummy_invitation(event, guest=None):
    """An unsaved invitation with a dead token, for previews and test sends."""
    guest = guest or Guest(first_name="Prénom", last_name="Nom")
    return Invitation(guest=guest, event=event, token=DUMMY_TOKEN)


SAVE_THE_DATE = Campaign(
    key="save_the_date",
    label="Save the date",
    template="guests/email_templates/save_the_date.html",
    subject_setting="SAVE_THE_DATE_SUBJECT",
)
INVITATION = Campaign(
    key="invitation",
    label="Invitation",
    template="guests/email_templates/invitation.html",
    subject_setting="INVITATION_SUBJECT",
)
PREPARATION = Campaign(
    key="preparation",
    label="Préparation",
    template="guests/email_templates/preparation.html",
    subject_setting="PREPARATION_SUBJECT",
    attending_only=True,
)
THANK_YOU = Campaign(
    key="thank_you",
    label="Remerciements",
    template="guests/email_templates/thank_you.html",
    subject_setting="THANK_YOU_SUBJECT",
    attending_only=True,
)
CAMPAIGNS = {c.key: c for c in (SAVE_THE_DATE, INVITATION, PREPARATION, THANK_YOU)}


def get_campaign_or_404(key):
    try:
        return CAMPAIGNS[key]
    except KeyError:
        raise Http404("Unknown campaign") from None
