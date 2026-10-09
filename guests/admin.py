from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from guests.models import Event, Family, Guest, Invitation, MealOption


class MealOptionInline(admin.TabularInline):
    model = MealOption
    extra = 1


@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "starts_at", "ends_at", "location", "order")
    prepopulated_fields = {"slug": ("name",)}
    inlines = [MealOptionInline]


class GuestInline(admin.TabularInline):
    model = Guest
    fields = ("first_name", "last_name", "email", "is_child")
    extra = 0
    show_change_link = True


@admin.register(Family)
class FamilyAdmin(admin.ModelAdmin):
    list_display = ("name", "member_count")
    search_fields = ("name",)
    inlines = [GuestInline]

    @admin.display(description="Membres")
    def member_count(self, family):
        return family.guest_set.count()


class InvitationInline(admin.TabularInline):
    model = Invitation
    fields = ("event", "is_attending", "meal_starter", "meal_main", "meal_dessert")
    extra = 0


@admin.register(Guest)
class GuestAdmin(UserAdmin):
    list_display = ("first_name", "last_name", "email", "family", "is_child", "is_staff")
    list_filter = ("is_child", "is_staff", "invitations__event")
    search_fields = ("first_name", "last_name", "email", "family__name")
    ordering = ("first_name", "last_name")
    readonly_fields = ("created",)
    inlines = [InvitationInline]
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Identité", {"fields": ("first_name", "last_name", "family", "is_child", "created")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": (
                    "first_name",
                    "last_name",
                    "email",
                    "family",
                    "is_child",
                    "usable_password",
                    "password1",
                    "password2",
                ),
            },
        ),
    )


@admin.register(Invitation)
class InvitationAdmin(admin.ModelAdmin):
    list_display = (
        "guest",
        "event",
        "is_attending",
        "responded_at",
        "save_the_date_sent",
        "invitation_sent",
        "invitation_opened",
        "preparation_sent",
        "thank_you_sent",
    )
    list_filter = ("event", "is_attending")
    search_fields = ("guest__first_name", "guest__last_name", "guest__email", "guest__family__name")
    readonly_fields = ("token", "responded_at")
    list_select_related = ("guest", "event")
