import logging

from django.conf import settings
from django.contrib.staticfiles.storage import staticfiles_storage

logger = logging.getLogger(__name__)


def _static_url(path):
    """URL of a static file, or "" (with a warning) when it is not configured or does not exist."""
    if not path:
        return ""
    try:
        return staticfiles_storage.url(path)
    except ValueError:
        logger.warning("Static file %s is configured but missing; ignoring it", path)
        return ""


def site(request):
    """Expose the (non-secret) site identity settings to every template."""
    return {
        "site_title": settings.SITE_TITLE,
        "couple_names": settings.COUPLE_NAMES,
        "support_email": settings.WEDDING_REPLY_EMAIL,
        "header_image_url": _static_url(settings.HEADER_IMAGE),
        "header_image_fit": settings.HEADER_IMAGE_FIT,
        "gift_pot_url": settings.GIFT_POT_URL,
        "rsvp_deadline": settings.RSVP_DEADLINE,
        "registration_enabled": bool(settings.REGISTRATION_CODE),
        "lychee_enabled": bool(settings.LYCHEE_URL),
    }
