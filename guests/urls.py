from django.urls import path

from guests import views

urlpatterns = [
    path("", views.home, name="home"),
    path("register/", views.register_request, name="register"),
    path("healthz", views.healthz, name="healthz"),
    # Personal links found in the e-mails (the token is secret and identifies one invitation).
    path("home/<str:token>/", views.magic_home, name="magic_home"),
    path("invite/<str:token>/", views.rsvp, name="rsvp"),
    path("invite/<str:token>/merci/", views.rsvp_confirm, name="rsvp_confirm"),
    path("photos/", views.photos, name="photos"),
    path("photos/<str:token>/", views.photos_link, name="photos_link"),
    # Staff only
    path("dashboard/", views.dashboard, name="dashboard"),
    path("dashboard/export/", views.export_guests, name="export_guests"),
    path("dashboard/preview/<str:campaign>/<slug:event>/", views.campaign_preview, name="campaign_preview"),
    path("dashboard/test/<str:campaign>/<slug:event>/", views.campaign_test, name="campaign_test"),
]
