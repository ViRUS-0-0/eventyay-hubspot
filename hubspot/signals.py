from django.dispatch import receiver
from django.urls import resolve
from django.utils.translation import gettext_lazy as _
from eventyay.control.signals import nav_event


@receiver(nav_event, dispatch_uid="hubspot_nav")
def control_nav_import(sender, request=None, **kwargs):
    url = resolve(request.path_info)
    return [
        {
            "label": _("Hubspot"),
            "url": "",
            "active": url.namespace == "plugins:hubspot"
            and url.url_name != "settings",
            "icon": "bar-chart",
        }
    ]