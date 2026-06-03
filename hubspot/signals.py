from django.dispatch import receiver
from django.urls import resolve
from django.utils.translation import gettext_lazy as _
from eventyay.control.signals import nav_event_settings

@receiver(nav_event_settings, dispatch_uid="hubspot_nav")
def navbar_info(sender, request, **kwargs):
    url = resolve(request.path_info)
    if not request.user.has_event_permission(
        request.organizer, request.event, "can_change_event_settings", request=request
    ):
        return []
    return [
        {
            "label": _("Hubspot"),
            "active": url.namespace == "plugins:hubspot"
            and url.url_name == "settings",
        }
    ]