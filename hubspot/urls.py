from django.urls import path
from hubspot.views import EventHubSpotSettingsView

urlpatterns = [
    path(
        "control/event/<orgslug:organizer>/<slug:event>/hubspot/",
        EventHubSpotSettingsView.as_view(),
        name="hubspot",
    ),
]
