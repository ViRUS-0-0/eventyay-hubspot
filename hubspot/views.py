from django.views.generic import TemplateView
from eventyay.control.permissions import EventPermissionRequiredMixin


class EventHubSpotSettingsView(EventPermissionRequiredMixin, TemplateView):
    """Landing page for HubSpot integration settings."""

    template_name = "hubspot/settings_landing.html"
    permission = "can_change_event_settings"
