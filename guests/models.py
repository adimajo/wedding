import secrets

from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
from django.db import models
from django.utils import timezone


def random_token():
    """Unguessable token used in the personal links of the e-mails."""
    return secrets.token_hex(16)


class Family(models.Model):
    """People who answer together (a couple, a household...)."""

    name = models.CharField("nom", max_length=200, unique=True)

    class Meta:
        verbose_name = "famille"
        verbose_name_plural = "familles"
        ordering = ["name"]

    def __str__(self):
        return self.name


class Event(models.Model):
    """One occasion of the wedding (civil ceremony, religious ceremony, party...). Guests are invited per event."""

    slug = models.SlugField(
        "identifiant",
        unique=True,
        help_text="Court et sans espace : utilisé dans les URL, les fichiers CSV (invited_<identifiant>) et le "
        "modèle de page partials/event_<identifiant>.html du dossier de contenu.",
    )
    name = models.CharField("nom", max_length=200)
    starts_at = models.DateTimeField("début", null=True, blank=True)
    ends_at = models.DateTimeField("fin", null=True, blank=True)
    location = models.CharField("lieu", max_length=300, blank=True)
    location_url = models.URLField("lien du lieu", blank=True)
    description = models.TextField(blank=True, help_text="Texte libre affiché dans la section de l'événement.")
    order = models.PositiveSmallIntegerField("ordre", default=0)

    class Meta:
        verbose_name = "événement"
        verbose_name_plural = "événements"
        ordering = ["order", "starts_at", "name"]

    def __str__(self):
        return self.name

    def meal_options_for(self, course):
        return [option for option in self.meal_options.all() if option.course == course]


class MealOption(models.Model):
    """A dish that guests can choose for an event."""

    STARTER = "starter"
    MAIN = "main"
    DESSERT = "dessert"
    COURSES = [(STARTER, "Entrée"), (MAIN, "Plat"), (DESSERT, "Dessert")]

    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="meal_options")
    course = models.CharField("service", max_length=10, choices=COURSES, default=MAIN)
    key = models.SlugField("identifiant", help_text="Utilisé dans les exports.")
    label = models.CharField("libellé", max_length=400)
    order = models.PositiveSmallIntegerField("ordre", default=0)

    class Meta:
        verbose_name = "choix de menu"
        verbose_name_plural = "choix de menu"
        ordering = ["event", "course", "order", "label"]
        constraints = [models.UniqueConstraint(fields=["event", "course", "key"], name="unique_meal_per_course")]

    def __str__(self):
        return f"{self.get_course_display()} - {self.label}"


class GuestManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, first_name, last_name="", email=None, password=None, **extra_fields):
        """Create a guest. Without a password the account can only be used through its personal links."""
        user = self.model(
            first_name=first_name,
            last_name=last_name,
            email=(email or "").strip().lower() or None,
            **extra_fields,
        )
        if password is None:
            user.set_unusable_password()
        else:
            user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, first_name, last_name, email, password=None, **extra_fields):
        if not email:
            raise ValueError("A staff account needs an email address")
        extra_fields["is_staff"] = True
        extra_fields["is_superuser"] = True
        return self.create_user(first_name, last_name, email, password, **extra_fields)


class Guest(AbstractBaseUser, PermissionsMixin):
    """
    A single guest. Guests normally never have a password: they use the personal links of the e-mails
    (see ``Invitation.token``).
    """

    first_name = models.CharField("prénom", max_length=150)
    last_name = models.CharField("nom", max_length=150, blank=True)
    email = models.EmailField(null=True, blank=True, unique=True, help_text="Facultatif, par exemple pour un enfant.")
    family = models.ForeignKey(Family, on_delete=models.SET_NULL, null=True, blank=True, verbose_name="famille")
    is_child = models.BooleanField("enfant", default=False, help_text="Pas de choix de menu demandé.")
    created = models.DateTimeField(default=timezone.now, editable=False)
    is_staff = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)

    REQUIRED_FIELDS = ["first_name", "last_name"]
    USERNAME_FIELD = "email"
    objects = GuestManager()

    class Meta:
        verbose_name = "invité"
        verbose_name_plural = "invités"
        ordering = ["first_name", "last_name"]

    def save(self, *args, **kwargs):
        # Lower-cased so that logging in does not depend on the case typed; None (not "") because several guests
        # without e-mail must not collide on the unique column.
        self.email = (self.email or "").strip().lower() or None
        super().save(*args, **kwargs)

    @property
    def name(self):
        return f"{self.first_name} {self.last_name}".strip()

    def get_full_name(self):
        return self.name

    def get_short_name(self):
        return self.first_name

    def __str__(self):
        return self.name


class Invitation(models.Model):
    """The invitation of one guest to one event: RSVP answer, meal choices and e-mail tracking."""

    guest = models.ForeignKey(Guest, on_delete=models.CASCADE, related_name="invitations")
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name="invitations")
    # Secret token of the personal links (RSVP page, site log-in); never shown to other guests.
    token = models.CharField(max_length=32, db_index=True, default=random_token, unique=True, editable=False)

    save_the_date_sent = models.DateTimeField(null=True, blank=True, default=None)
    save_the_date_opened = models.DateTimeField(null=True, blank=True, default=None)
    invitation_sent = models.DateTimeField(null=True, blank=True, default=None)
    invitation_opened = models.DateTimeField(null=True, blank=True, default=None)
    preparation_sent = models.DateTimeField(null=True, blank=True, default=None)
    preparation_opened = models.DateTimeField(null=True, blank=True, default=None)
    thank_you_sent = models.DateTimeField(null=True, blank=True, default=None)
    thank_you_opened = models.DateTimeField(null=True, blank=True, default=None)

    is_attending = models.BooleanField("présent(e)", null=True, blank=True, default=None)
    responded_at = models.DateTimeField(null=True, blank=True, default=None, editable=False)
    meal_starter = models.ForeignKey(
        MealOption, on_delete=models.SET_NULL, null=True, blank=True, related_name="+", verbose_name="entrée"
    )
    meal_main = models.ForeignKey(
        MealOption, on_delete=models.SET_NULL, null=True, blank=True, related_name="+", verbose_name="plat"
    )
    meal_dessert = models.ForeignKey(
        MealOption, on_delete=models.SET_NULL, null=True, blank=True, related_name="+", verbose_name="dessert"
    )
    comments = models.TextField("commentaires", blank=True)

    class Meta:
        verbose_name = "invitation"
        verbose_name_plural = "invitations"
        ordering = ["event", "guest"]
        constraints = [models.UniqueConstraint(fields=["guest", "event"], name="one_invitation_per_guest_and_event")]

    def __str__(self):
        return f"{self.guest} - {self.event}"

    def family_invitations(self):
        """Invitations to the same event of the whole family (the guest alone when there is no family)."""
        queryset = Invitation.objects.filter(event=self.event).select_related("guest")
        if self.guest.family_id is None:
            return queryset.filter(pk=self.pk)
        return queryset.filter(guest__family_id=self.guest.family_id, guest__is_active=True).order_by(
            "guest__is_child", "guest__first_name", "guest__pk"
        )
