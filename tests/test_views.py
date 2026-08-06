import pytest
from django.urls import reverse
from unittest import mock
from django_scopes import scope
from django.utils.timezone import now
from datetime import timedelta
from eventyay.base.models import Event, Organizer
from hubspot.models import (
    HubSpotEventSettings,
    HubSpotOAuthToken,
    ObjectTypeMapping,
    OrganizerHubSpotSettings,
    OrganizerHubSpotOAuthToken,
)
import requests


@pytest.mark.django_db
def test_hubspot_settings_view_logged_out(client, organizer, event, settings):
    settings.SITE_URL = "https://testserver"
    url = reverse(
        "plugins:hubspot:hubspot",
        kwargs={"organizer": organizer.slug, "event": event.slug},
    )
    response = client.get(url)
    assert response.status_code == 302
    assert "login" in response.url


@pytest.mark.django_db
def test_hubspot_settings_view_wrong_organizer(
    logged_in_client, organizer, event, settings
):
    settings.SITE_URL = "https://testserver"
    url = reverse(
        "plugins:hubspot:hubspot",
        kwargs={"organizer": organizer.slug, "event": event.slug},
    )
    response = logged_in_client.get(url)
    assert response.status_code in [403, 404]


@pytest.mark.django_db
def test_hubspot_settings_view_correct_organizer(
    logged_in_organizer_client, organizer, event, settings
):
    settings.SITE_URL = "https://testserver"
    url = reverse(
        "plugins:hubspot:hubspot",
        kwargs={"organizer": organizer.slug, "event": event.slug},
    )
    response = logged_in_organizer_client.get(url)
    assert response.status_code == 200


@pytest.mark.django_db
def test_hubspot_disconnect_view_not_connected(
    logged_in_organizer_client, organizer, event, settings
):
    settings.SITE_URL = "https://testserver"
    url = reverse(
        "plugins:hubspot:disconnect",
        kwargs={"organizer": organizer.slug, "event": event.slug},
    )
    response = logged_in_organizer_client.post(url)
    assert response.status_code == 302
    assert response.url == reverse(
        "plugins:hubspot:hubspot",
        kwargs={"organizer": organizer.slug, "event": event.slug},
    )


@pytest.mark.django_db
@mock.patch("hubspot.views.requests.delete")
def test_hubspot_disconnect_view_connected(
    mock_delete, logged_in_organizer_client, organizer, event, settings
):
    settings.SITE_URL = "https://testserver"
    with scope(organizer=event.organizer):
        HubSpotOAuthToken.objects.create(
            event=event, access_token="old_access", refresh_token="old_refresh"
        )

    mock_response = mock.Mock()
    mock_response.ok = True
    mock_delete.return_value = mock_response

    with scope(organizer=event.organizer):
        from django.core.cache import cache

        cache.set(f"hubspot_properties_{event.id}_contacts", [{"key": "test"}])
        cache.set(f"hubspot_properties_error_{event.id}_contacts", "Error")

    url = reverse(
        "plugins:hubspot:disconnect",
        kwargs={"organizer": organizer.slug, "event": event.slug},
    )
    response = logged_in_organizer_client.post(url)

    assert response.status_code == 302
    assert response.url == reverse(
        "plugins:hubspot:hubspot",
        kwargs={"organizer": organizer.slug, "event": event.slug},
    )

    with scope(organizer=event.organizer):
        assert not HubSpotOAuthToken.objects.filter(event=event).exists()
        from django.core.cache import cache

        assert not cache.get(f"hubspot_properties_{event.id}_contacts")
        assert not cache.get(f"hubspot_properties_error_{event.id}_contacts")


@pytest.mark.django_db
@mock.patch("hubspot.views.requests.delete")
def test_hubspot_disconnect_view_revoke_failure_still_clears(
    mock_delete, logged_in_organizer_client, organizer, event, settings
):
    settings.SITE_URL = "https://testserver"
    with scope(organizer=event.organizer):
        HubSpotOAuthToken.objects.create(
            event=event, access_token="old_access", refresh_token="old_refresh"
        )

    # Simulate a network error or 500 from HubSpot

    mock_delete.side_effect = requests.RequestException("Timeout")

    url = reverse(
        "plugins:hubspot:disconnect",
        kwargs={"organizer": organizer.slug, "event": event.slug},
    )
    response = logged_in_organizer_client.post(url)

    assert response.status_code == 302

    with scope(organizer=event.organizer):
        # Local state should still be cleared
        assert not HubSpotOAuthToken.objects.filter(event=event).exists()


@pytest.mark.django_db
def test_hubspot_settings_save_auto_sync_audit_log(
    logged_in_organizer_client, organizer, event, settings
):
    from hubspot.models import AuditLog, AuditAction, HubSpotEventSettings

    settings.SITE_URL = "https://testserver"

    # Get settings or create
    with scope(organizer=event.organizer):
        HubSpotEventSettings.objects.get_or_create(
            event=event, defaults={"auto_sync_enabled": True}
        )

    url = reverse(
        "plugins:hubspot:hubspot",
        kwargs={"organizer": organizer.slug, "event": event.slug},
    )

    # Disable auto_sync
    response = logged_in_organizer_client.post(
        url,
        {
            "form_type": "settings",
            "auto_sync_enabled": "False",  # checkbox off/False
            # Add other fields if necessary
        },
    )
    assert response.status_code == 302

    with scope(organizer=event.organizer):
        assert AuditLog.objects.filter(
            event=event, action=AuditAction.AUTO_SYNC_DISABLED
        ).exists()

    # Enable auto_sync again
    response = logged_in_organizer_client.post(
        url,
        {
            "form_type": "settings",
            "auto_sync_enabled": "on",  # checkbox on
        },
    )
    assert response.status_code == 302

    with scope(organizer=event.organizer):
        assert AuditLog.objects.filter(
            event=event, action=AuditAction.AUTO_SYNC_ENABLED
        ).exists()


@pytest.mark.django_db
def test_organizer_settings_view_lists_only_organizer_events(
    logged_in_organizer_client, organizer, event, settings, user
):
    settings.SITE_URL = "https://testserver"
    with scope(organizer=organizer):
        event2 = Event.objects.create(
            organizer=organizer,
            name="Test Event 2",
            slug="test-event-2",
            date_from=now(),
            date_to=now() + timedelta(days=1),
            currency="USD",
            live=True,
            plugins="hubspot",
        )

    # Another organizer and event
    other_organizer = Organizer.objects.create(name="Other Org", slug="other-org")
    with scope(organizer=other_organizer):
        other_event = Event.objects.create(
            organizer=other_organizer,
            name="Other Event",
            slug="other-event",
            date_from=now(),
            date_to=now() + timedelta(days=1),
            currency="USD",
            live=True,
            plugins="hubspot",
        )

    url = reverse("plugins:hubspot:org_hubspot", kwargs={"organizer": organizer.slug})
    response = logged_in_organizer_client.get(url)
    assert response.status_code == 200
    events_in_context = response.context["events"]
    event_ids = {e.id for e in events_in_context}
    assert event.id in event_ids
    assert event2.id in event_ids
    assert other_event.id not in event_ids


@pytest.mark.django_db
def test_organizer_settings_view_connection_and_mapping_status(
    logged_in_organizer_client, organizer, event, settings
):
    settings.SITE_URL = "https://testserver"
    with scope(organizer=organizer):
        # Setup event with custom token and custom mapping
        HubSpotOAuthToken.objects.create(
            event=event,
            access_token="token",
            refresh_token="ref",
            expires_at=now() + timedelta(hours=1),
        )
        ObjectTypeMapping.objects.create(
            event=event,
            eventyay_object_type="order",
            hubspot_object_type="deal",
        )

        # Create second event with no token/mapping, relying on organizer fallback
        event2 = Event.objects.create(
            organizer=organizer,
            name="Test Event 2",
            slug="test-event-2",
            date_from=now(),
            date_to=now() + timedelta(days=1),
            currency="USD",
            live=True,
            plugins="hubspot",
        )
        OrganizerHubSpotOAuthToken.objects.create(
            organizer=organizer,
            access_token="org_token",
            refresh_token="org_ref",
            expires_at=now() + timedelta(hours=1),
        )
        OrganizerHubSpotSettings.objects.create(organizer=organizer, sync_enabled=True)

    url = reverse("plugins:hubspot:org_hubspot", kwargs={"organizer": organizer.slug})
    response = logged_in_organizer_client.get(url)
    assert response.status_code == 200
    events_dict = {e.id: e for e in response.context["events"]}

    e1 = events_dict[event.id]
    assert e1.connection_badge_class == "success"
    assert "Event token" in str(e1.connection_status_text)
    assert e1.mapping_badge_class == "primary"
    assert "Custom" in str(e1.mapping_status_text)

    e2 = events_dict[event2.id]
    assert e2.connection_badge_class == "info"
    assert "Organizer fallback" in str(e2.connection_status_text)
    assert e2.mapping_badge_class == "default"
    assert "Organizer default" in str(e2.mapping_status_text)

    # Now disable sync for event2 specifically
    with scope(organizer=organizer):
        HubSpotEventSettings.objects.update_or_create(
            event=event2, defaults={"sync_enabled": False}
        )

    response = logged_in_organizer_client.get(url)
    assert response.status_code == 200
    events_dict = {e.id: e for e in response.context["events"]}
    e2_disabled = events_dict[event2.id]
    assert e2_disabled.connection_badge_class == "muted"
    assert "Not connected" in str(e2_disabled.connection_status_text)


@pytest.mark.django_db
def test_organizer_settings_view_single_save_action(
    logged_in_organizer_client, organizer, event, settings
):
    settings.SITE_URL = "https://testserver"
    with scope(organizer=organizer):
        event2 = Event.objects.create(
            organizer=organizer,
            name="Test Event 2",
            slug="test-event-2",
            date_from=now(),
            date_to=now() + timedelta(days=1),
            currency="USD",
            live=True,
            plugins="hubspot",
        )

    url = reverse("plugins:hubspot:org_hubspot", kwargs={"organizer": organizer.slug})
    response = logged_in_organizer_client.post(
        url,
        {
            "form_type": "events_toggle",
            "event_ids": [event.id, event2.id],
            f"event_sync_enabled_{event.id}": "1",
            # event2 checkbox is unchecked (missing from POST)
        },
    )
    assert response.status_code == 302

    with scope(organizer=organizer):
        ev1_settings = HubSpotEventSettings.objects.get(event=event)
        assert ev1_settings.sync_enabled is True
        ev2_settings = HubSpotEventSettings.objects.get(event=event2)
        assert ev2_settings.sync_enabled is False


@pytest.mark.django_db
def test_event_hubspot_settings_view_organizer_fallback(
    logged_in_organizer_client, organizer, event, settings
):
    settings.SITE_URL = "https://testserver"
    with scope(organizer=organizer):
        OrganizerHubSpotOAuthToken.objects.create(
            organizer=organizer,
            access_token="org_access_token",
            refresh_token="org_refresh_token",
            expires_at=now() + timedelta(days=1),
            hub_id="123456",
            hub_name="company.com",
        )
        OrganizerHubSpotSettings.objects.create(organizer=organizer, sync_enabled=True)

    url = reverse(
        "plugins:hubspot:hubspot",
        kwargs={"organizer": organizer.slug, "event": event.slug},
    )
    response = logged_in_organizer_client.get(url)
    assert response.status_code == 200
    assert response.context["is_connected"] is True
    assert response.context["connection_source"] == "organizer"
    assert response.context["hub_id"] == "123456"

    # Now disable sync specifically for this event
    with scope(organizer=organizer):
        HubSpotEventSettings.objects.update_or_create(
            event=event, defaults={"sync_enabled": False}
        )

    response = logged_in_organizer_client.get(url)
    assert response.status_code == 200
    assert response.context["is_connected"] is False


@pytest.mark.django_db
def test_organizer_settings_view_your_events_panel_visibility(
    logged_in_organizer_client, organizer, settings
):
    settings.SITE_URL = "https://testserver"
    url = reverse("plugins:hubspot:org_hubspot", kwargs={"organizer": organizer.slug})

    # When main toggle is off (default), Your Events panel should not be visible in HTML
    response = logged_in_organizer_client.get(url)
    assert response.status_code == 200
    assert b"Your Events" not in response.content

    # When main toggle is enabled, Your Events panel should be visible in HTML
    with scope(organizer=organizer):
        OrganizerHubSpotSettings.objects.update_or_create(
            organizer=organizer, defaults={"sync_enabled": True}
        )

    response = logged_in_organizer_client.get(url)
    assert response.status_code == 200
    assert b"Your Events" in response.content
    assert b"Sync Enabled" in response.content
