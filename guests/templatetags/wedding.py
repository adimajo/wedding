import re

from django import template
from django.contrib.staticfiles.storage import staticfiles_storage
from django.template.loader import select_template

register = template.Library()


def content_id(path):
    """Content-ID of an inline e-mail image (``cid:`` reference), safe for any static path."""
    return re.sub(r"[^A-Za-z0-9._-]", "_", path)


@register.simple_tag(takes_context=True)
def email_image(context, path):
    """URL of an image for the HTML e-mails.

    In an e-mail the image is embedded: the tag returns a ``cid:`` reference and records the path in
    ``inline_images`` so that the campaign attaches the file. In a browser preview it returns the static URL.
    """
    if context.get("email_mode"):
        images = context.get("inline_images")
        if images is not None and path not in images:
            images.append(path)
        return f"cid:{content_id(path)}"
    return staticfiles_storage.url(path)


@register.simple_tag(takes_context=True)
def event_section(context, event):
    """Render the section of an event: ``partials/event_<slug>.html`` when it exists, else the generic one."""
    chosen = select_template([f"partials/event_{event.slug}.html", "partials/event.html"])
    with context.push(event=event):
        return chosen.render(context.flatten(), request=context.get("request"))
