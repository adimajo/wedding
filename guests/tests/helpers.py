from guests.models import Event, Family, Guest, Invitation, MealOption


def make_event(slug="ceremony", name="Cérémonie", menu=False, **kwargs):
    event = Event.objects.create(slug=slug, name=name, **kwargs)
    if menu:
        MealOption.objects.create(event=event, course=MealOption.MAIN, key="beef", label="Boeuf")
        MealOption.objects.create(event=event, course=MealOption.MAIN, key="veggie", label="Végétarien")
        MealOption.objects.create(event=event, course=MealOption.DESSERT, key="cake", label="Gâteau")
    return event


def make_family(event, *people, family="The Starks"):
    """People are (first_name, last_name, email[, is_child]); returns the invitations in order."""
    family_object = Family.objects.get_or_create(name=family)[0]
    invitations = []
    for first_name, last_name, email, *rest in people:
        guest = Guest.objects.create_user(
            first_name, last_name, email, family=family_object, is_child=bool(rest and rest[0])
        )
        invitations.append(Invitation.objects.create(guest=guest, event=event))
    return invitations
