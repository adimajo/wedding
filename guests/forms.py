from django import forms
from django.conf import settings
from django.contrib.auth.forms import PasswordResetForm, UserCreationForm
from django.utils import timezone
from django.utils.crypto import constant_time_compare

from guests.models import Guest, MealOption


class MealChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        return obj.label


class RsvpForm(forms.Form):
    """The answer of one guest to one invitation (several of them are shown on the same page for a family)."""

    attending = forms.TypedChoiceField(
        choices=[("yes", "sera présent(e)"), ("no", "ne sera pas présent(e)")],
        coerce=lambda value: value == "yes",
        widget=forms.RadioSelect(attrs={"class": "form-check-input attending-radio"}),
        error_messages={"required": "Merci d'indiquer si cette personne sera présente."},
    )
    meal_starter = MealChoiceField(
        queryset=MealOption.objects.none(),
        required=False,
        empty_label=None,
        widget=forms.RadioSelect(attrs={"class": "form-check-input"}),
    )
    meal_main = MealChoiceField(
        queryset=MealOption.objects.none(),
        required=False,
        empty_label=None,
        widget=forms.RadioSelect(attrs={"class": "form-check-input"}),
    )
    meal_dessert = MealChoiceField(
        queryset=MealOption.objects.none(),
        required=False,
        empty_label=None,
        widget=forms.RadioSelect(attrs={"class": "form-check-input"}),
    )

    COURSE_FIELDS = {
        MealOption.STARTER: "meal_starter",
        MealOption.MAIN: "meal_main",
        MealOption.DESSERT: "meal_dessert",
    }

    def __init__(self, *args, invitation, **kwargs):
        self.invitation = invitation
        initial = kwargs.setdefault("initial", {})
        if invitation.is_attending is not None:
            initial["attending"] = "yes" if invitation.is_attending else "no"
        super().__init__(*args, **kwargs)
        self.active_courses = []
        for course, field_name in self.COURSE_FIELDS.items():
            options = MealOption.objects.filter(event=invitation.event, course=course)
            field = self.fields[field_name]
            field.queryset = options
            field.label = dict(MealOption.COURSES)[course]
            field.initial = getattr(invitation, f"{field_name}_id")
            if options.exists() and not invitation.guest.is_child:
                self.active_courses.append(field_name)
            else:
                del self.fields[field_name]

    @property
    def meal_fields(self):
        return [self[name] for name in self.active_courses]

    def clean(self):
        cleaned = super().clean()
        attending = cleaned.get("attending")
        if attending is None:
            return cleaned
        for name in self.active_courses:
            if attending and not cleaned.get(name):
                self.add_error(name, "Merci de choisir un menu.")
            elif not attending:
                cleaned[name] = None
        return cleaned

    def save(self):
        invitation = self.invitation
        invitation.is_attending = self.cleaned_data["attending"]
        for name in self.COURSE_FIELDS.values():
            setattr(invitation, name, self.cleaned_data.get(name))
        invitation.responded_at = timezone.now()
        invitation.save()
        return invitation


class CommentForm(forms.Form):
    comments = forms.CharField(required=False, max_length=2000, widget=forms.TextInput)

    def append_to(self, invitation):
        comment = self.cleaned_data["comments"].strip()
        if comment:
            invitation.comments = f"{invitation.comments}; {comment}" if invitation.comments else comment
            invitation.save(update_fields=["comments"])


class RegisterForm(UserCreationForm):
    """Account creation, only for people who know the shared registration code."""

    first_name = forms.CharField(label="Prénom", max_length=150)
    last_name = forms.CharField(label="Nom", max_length=150)
    email = forms.EmailField(label="Email")
    registration_code = forms.CharField(
        label="Code d'accès",
        help_text="Le code figure dans le message que vous avez reçu de notre part.",
        strip=True,
    )

    class Meta:
        model = Guest
        fields = ["first_name", "last_name", "email", "password1", "password2"]

    def clean_registration_code(self):
        code = self.cleaned_data["registration_code"]
        expected = settings.REGISTRATION_CODE
        if not expected or not constant_time_compare(code.casefold(), expected.casefold()):
            raise forms.ValidationError("Code d'accès incorrect.")
        return code

    def clean_email(self):
        email = Guest.objects.normalize_email(self.cleaned_data["email"])
        if Guest.objects.filter(email__iexact=email, is_active=True).exists():
            raise forms.ValidationError(
                "Un compte existe déjà avec cet email : connectez-vous ou réinitialisez votre mot de passe."
            )
        return email


class GuestPasswordResetForm(PasswordResetForm):
    """Password reset that also works for guests imported without a password."""

    def get_users(self, email):
        return Guest.objects.filter(email__iexact=email, is_active=True)

    def save(self, *args, extra_email_context=None, **kwargs):
        # Built from the settings at call time (the proxy-provided Host header is not trusted for links).
        extra_email_context = {
            **(extra_email_context or {}),
            "site_title": settings.SITE_TITLE,
            "site_url": settings.SITE_URL,
        }
        return super().save(*args, extra_email_context=extra_email_context, **kwargs)
