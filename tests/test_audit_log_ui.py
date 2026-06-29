import pytest
from django.urls import reverse
from django_scopes import scope
from eventyay.base.models import Event
from hubspot.models import (
    AuditLog,
    SyncLog,
    AuditAction,
    SyncAction,
    SyncDirection,
    SyncStatus,
)


@pytest.mark.django_db
def test_hubspot_settings_recent_activity_preview(
    logged_in_organizer_client, organizer, event, settings
):
    settings.SITE_URL = "https://testserver"

    with scope(organizer=event.organizer):
        for i in range(10):
            AuditLog.objects.create(
                organizer=event.organizer,
                event=event,
                action=(
                    AuditAction.CONNECT if i % 2 == 0 else AuditAction.MAPPING_UPDATED
                ),
                ip_address="127.0.0.1",
            )

    url = reverse(
        "plugins:hubspot:hubspot",
        kwargs={"organizer": organizer.slug, "event": event.slug},
    )
    response = logged_in_organizer_client.get(url)
    assert response.status_code == 200

    # Check that the preview shows at most 5 entries
    content = response.content.decode()
    assert "Recent Activity" in content

    # We should have 5 items in the table body
    # Since we created 10, the preview only shows 5
    assert content.count('<td class="text-muted">') == 5


@pytest.mark.django_db
def test_hubspot_logs_view_all_entries(
    logged_in_organizer_client, organizer, event, settings
):
    settings.SITE_URL = "https://testserver"

    with scope(organizer=event.organizer):

        AuditLog.objects.create(
            organizer=event.organizer,
            event=event,
            action=AuditAction.MAPPING_UPDATED,
            ip_address="127.0.0.1",
        )
        SyncLog.objects.create(
            event=event,
            action=SyncAction.CREATE,
            direction=SyncDirection.PUSH,
            status=SyncStatus.SUCCESS,
        )

    url = reverse(
        "plugins:hubspot:logs",
        kwargs={"organizer": organizer.slug, "event": event.slug},
    )

    # Test all activities
    response = logged_in_organizer_client.get(url)
    assert response.status_code == 200
    content = response.content.decode()
    assert "Field mapping settings were updated" in content
    assert "Object synced to HubSpot successfully" in content
    assert content.count('<td class="text-muted">') == 2

    # Test sync filter
    response_sync = logged_in_organizer_client.get(url + "?type=sync")
    assert response_sync.status_code == 200
    assert "Object synced to HubSpot successfully" in response_sync.content.decode()
    assert response_sync.content.decode().count('<td class="text-muted">') == 1

    # Test settings filter
    response_sett = logged_in_organizer_client.get(url + "?type=settings")
    assert response_sett.status_code == 200
    assert "Field mapping settings were updated" in response_sett.content.decode()
    assert response_sett.content.decode().count('<td class="text-muted">') == 1


@pytest.mark.django_db
def test_hubspot_logs_view_other_event_entries_not_shown(
    logged_in_organizer_client, organizer, event, settings
):
    settings.SITE_URL = "https://testserver"

    event2 = Event.objects.create(
        organizer=organizer, name="Event 2", slug="event2", date_from=event.date_from
    )

    with scope(organizer=event.organizer):
        AuditLog.objects.create(
            organizer=event.organizer,
            event=event2,  # Using different event
            action=AuditAction.MAPPING_UPDATED,
            ip_address="127.0.0.1",
        )

    url = reverse(
        "plugins:hubspot:logs",
        kwargs={"organizer": organizer.slug, "event": event.slug},
    )
    response = logged_in_organizer_client.get(url)
    assert response.status_code == 200
    assert "Field mapping settings were updated" not in response.content.decode()
    assert response.content.decode().count('<td class="text-muted">') == 0


@pytest.mark.django_db
def test_hubspot_logs_view_permission_denied(
    logged_in_client, organizer, event, settings
):
    settings.SITE_URL = "https://testserver"
    url = reverse(
        "plugins:hubspot:logs",
        kwargs={"organizer": organizer.slug, "event": event.slug},
    )
    # Logged in client who is not organizer for the event
    response = logged_in_client.get(url)
    assert response.status_code in [403, 404]
