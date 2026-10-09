import csv

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.db import connection
from django.http import Http404, HttpResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from guests import csv_import, lychee
from guests.campaigns import CAMPAIGNS, dummy_invitation, get_campaign_or_404
from guests.forms import CommentForm, RegisterForm, RsvpForm
from guests.models import Event, Invitation

BACKEND = "django.contrib.auth.backends.ModelBackend"


def _invitation_or_404(token):
    """The invitation behind a personal link; links of deactivated guests stop working."""
    try:
        return Invitation.objects.select_related("guest", "event").get(token=token, guest__is_active=True)
    except Invitation.DoesNotExist:
        raise Http404("Unknown link") from None


@require_GET
def healthz(request):
    """Liveness/readiness probe used by the container healthcheck."""
    with connection.cursor() as cursor:
        cursor.execute("SELECT 1")
    return HttpResponse("ok", content_type="text/plain")


def register_request(request):
    if not settings.REGISTRATION_CODE:
        raise Http404("Registration is disabled")
    if request.method == "POST":
        form = RegisterForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user, backend=BACKEND)
            messages.success(request, "Votre compte a bien été créé.")
            return redirect("home")
        messages.error(request, "Inscription impossible : merci de corriger les erreurs ci-dessous.")
    else:
        form = RegisterForm()
    return render(request, "register.html", {"register_form": form})


@login_required
def home(request):
    invitations = (
        Invitation.objects.filter(guest=request.user)
        .select_related("event")
        .prefetch_related("event__meal_options")
        .order_by("event__order", "event__starts_at")
    )
    return render(
        request,
        "home.html",
        {"invitations": invitations, "events": [invitation.event for invitation in invitations]},
    )


def magic_home(request, token):
    """Personal link of the e-mails: logs the guest in and records which campaign was opened."""
    invitation = _invitation_or_404(token)
    campaign = CAMPAIGNS.get(request.GET.get("c", ""))
    if campaign:
        campaign.mark_opened(invitation)
    login(request, invitation.guest, backend=BACKEND)
    return redirect("home")


def photos_link(request, token):
    """Personal link to the photo gallery (thank-you e-mail): logs the guest in, then opens the gallery."""
    invitation = _invitation_or_404(token)
    login(request, invitation.guest, backend=BACKEND)
    return redirect("photos")


@login_required
def photos(request):
    """Log the guest in to the Lychee gallery and send them there."""
    if not lychee.is_enabled():
        raise Http404("No photo gallery configured")
    try:
        cookies = lychee.login_guest(request.user)
    except lychee.LycheeError:
        messages.error(request, "La galerie photo est momentanément indisponible, merci de réessayer plus tard.")
        return redirect("home")
    response = HttpResponseRedirect(f"{settings.LYCHEE_URL}/")
    for name, value in cookies.items():
        response.set_cookie(
            name,
            value,
            path="/",
            secure=settings.SESSION_COOKIE_SECURE if not settings.DEBUG else False,
            httponly=name != "XSRF-TOKEN",
            samesite="Lax",
        )
    return response


def rsvp(request, token):
    """The RSVP page: one answer per member of the family invited to the event."""
    invitation = _invitation_or_404(token)
    login(request, invitation.guest, backend=BACKEND)
    CAMPAIGNS["invitation"].mark_opened(invitation)
    invitations = list(invitation.family_invitations())
    if request.method == "POST":
        forms = [RsvpForm(request.POST, prefix=f"inv{item.pk}", invitation=item) for item in invitations]
        comment_form = CommentForm(request.POST)
        if all([form.is_valid() for form in forms]) and comment_form.is_valid():
            for form in forms:
                form.save()
            comment_form.append_to(invitation)
            return redirect("rsvp_confirm", token=token)
    else:
        forms = [RsvpForm(prefix=f"inv{item.pk}", invitation=item) for item in invitations]
        comment_form = CommentForm()
    return render(
        request,
        "guests/rsvp.html",
        {"invitation": invitation, "event": invitation.event, "forms": forms, "comment_form": comment_form},
    )


def rsvp_confirm(request, token):
    invitation = _invitation_or_404(token)
    anyone_attending = invitation.family_invitations().filter(is_attending=True).exists()
    return render(
        request,
        "guests/rsvp_confirmation.html",
        {"invitation": invitation, "event": invitation.event, "anyone_attending": anyone_attending},
    )


@staff_member_required
def dashboard(request):
    events = []
    for event in Event.objects.all():
        invitations = Invitation.objects.filter(event=event, guest__is_active=True).select_related("guest")
        attending = invitations.filter(is_attending=True)
        courses = set(event.meal_options.values_list("course", flat=True))
        events.append(
            {
                "event": event,
                "total": invitations.count(),
                "attending": attending.count(),
                "declined": invitations.filter(is_attending=False).count(),
                "pending": invitations.filter(is_attending=None).count(),
                "unopened": invitations.filter(invitation_opened=None),
                "unanswered": invitations.filter(is_attending=None).exclude(invitation_opened=None),
                "without_meal": [inv for inv in attending.filter(guest__is_child=False) if _missing_meal(inv, courses)],
                "meals": _meal_breakdown(attending, event),
            }
        )
    return render(request, "guests/dashboard.html", {"events": events, "campaigns": CAMPAIGNS.values()})


def _missing_meal(invitation, courses):
    return any(getattr(invitation, f"meal_{course}_id") is None for course in courses)


def _meal_breakdown(attending, event):
    return [
        {"option": option, "count": attending.filter(**{f"meal_{option.course}": option}).count()}
        for option in event.meal_options.all()
    ]


@staff_member_required
def campaign_preview(request, campaign, event):
    selected = get_campaign_or_404(campaign)
    return HttpResponse(selected.render_preview(get_object_or_404(Event, slug=event)))


@staff_member_required
@require_POST
def campaign_test(request, campaign, event):
    """Send the campaign e-mail to the requesting staff member only (with their own invitation if any)."""
    selected = get_campaign_or_404(campaign)
    event_object = get_object_or_404(Event, slug=event)
    invitation = Invitation.objects.filter(guest=request.user, event=event_object).first() or dummy_invitation(
        event_object, request.user
    )
    if not request.user.email:
        messages.error(request, "Votre compte n'a pas d'adresse e-mail.")
        return redirect("dashboard")
    selected.build_message(invitation, to=[request.user.email], cc=[]).send()
    messages.success(request, f"E-mail de test envoyé à {request.user.email}.")
    return redirect("dashboard")


@staff_member_required
def export_guests(request):
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = 'attachment; filename="guests.csv"'
    csv_import.write_export(csv.writer(response))
    return response
