import pytest
from django.urls import reverse
from unittest import mock
from django_scopes import scope
from hubspot.models import HubSpotOAuthToken, HubSpotProperty, HubSpotPropertySyncState
import uuid
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
        batch = uuid.uuid4()
        HubSpotProperty.objects.create(
            event=event, object_type="contact", key="test", sync_batch=batch
        )
        HubSpotPropertySyncState.objects.create(
            event=event, object_type="contact", sync_batch=batch
        )

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
        assert not HubSpotProperty.objects.filter(event=event).exists()
        assert not HubSpotPropertySyncState.objects.filter(event=event).exists()


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
