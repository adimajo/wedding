from django.test import TestCase, override_settings

PLAIN_STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}


@override_settings(
    STORAGES=PLAIN_STORAGES,
    REGISTRATION_CODE="Sesame",
    EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
    WEDDING_CC_LIST=["cc@example.org"],
    WEDDING_REPLY_EMAIL="contact@example.org",
    DEFAULT_FROM_EMAIL="Alex & Sam <alex@example.org>",
    SITE_URL="https://wedding.example.org",
    COUPLE_NAMES="Alex et Sam",
    SITE_TITLE="Notre mariage",
    RSVP_DEADLINE="",
    EMAIL_HERO_IMAGE="",
    EMAIL_HEADER_IMAGE="",
    HEADER_IMAGE="",
    HEADER_IMAGE_FIT="cover",
    GIFT_POT_URL="",
    LYCHEE_URL="",
    LYCHEE_API_URL="",
)
class AppTestCase(TestCase):
    """Base class: no static manifest needed, in-memory mail, known registration code, no gallery."""
