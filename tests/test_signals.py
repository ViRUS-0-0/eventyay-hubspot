import datetime
from unittest import mock

import pytest
from django.utils.timezone import now
from django_scopes import scopes_disabled

from hubspot.models import HubSpotEventSettings
from hubspot.signals import _enqueue_hubspot_sync


@pytest.fixture(autouse=True)
def disable_scopes():
    with scopes_disabled():
        from django.core.cache import cache

        cache.clear()
        yield


@pytest.mark.django_db
@mock.patch("hubspot.signals.sync_order_to_hubspot.apply_async")
def test_enqueue_sync_skipped_if_disabled(mock_apply, event, order):
    order.status = "p"
    # No settings
    _enqueue_hubspot_sync(None, order)
    mock_apply.assert_not_called()

    # Disabled
    HubSpotEventSettings.objects.create(event=event, sync_enabled=False)
    _enqueue_hubspot_sync(None, order)
    mock_apply.assert_not_called()


@pytest.mark.django_db
@mock.patch("hubspot.signals.sync_order_to_hubspot.apply_async")
def test_enqueue_sync_success(mock_apply, event, order, django_capture_on_commit_callbacks):
    HubSpotEventSettings.objects.create(event=event, sync_enabled=True)
    from hubspot.models import HubSpotOAuthToken

    HubSpotOAuthToken.objects.create(
        event=event,
        access_token="valid_access",
        refresh_token="valid_refresh",
        expires_at=now() + datetime.timedelta(hours=1),
    )
    order.status = "p"
    with django_capture_on_commit_callbacks(execute=True):
        _enqueue_hubspot_sync(None, order)
    mock_apply.assert_called_once_with(args=[order.id, event.id], countdown=5)


@pytest.mark.django_db
@mock.patch("hubspot.signals.sync_order_to_hubspot.apply_async")
def test_enqueue_sync_auto_sync_disabled(mock_apply, event, order, django_capture_on_commit_callbacks):
    from hubspot.models import SyncLog, SyncStatus

    HubSpotEventSettings.objects.create(event=event, sync_enabled=True, auto_sync_enabled=False)
    from hubspot.models import HubSpotOAuthToken

    HubSpotOAuthToken.objects.create(
        event=event,
        access_token="valid_access",
        refresh_token="valid_refresh",
        expires_at=now() + datetime.timedelta(hours=1),
    )

    order.status = "p"
    with django_capture_on_commit_callbacks(execute=True):
        _enqueue_hubspot_sync(None, order)
    mock_apply.assert_not_called()
    assert SyncLog.objects.filter(event=event, status=SyncStatus.PENDING).exists()


@pytest.mark.django_db
def test_event_created_bootstraps_hubspot_when_organizer_enabled(organizer):
    from eventyay.base.models import Event

    from hubspot.models import OrganizerHubSpotSettings

    OrganizerHubSpotSettings.objects.create(organizer=organizer, sync_enabled=True)

    event = Event.objects.create(
        organizer=organizer,
        name="Test Event",
        slug="test-event",
        date_from=now(),
        live=False,
    )

    settings = HubSpotEventSettings.objects.filter(event=event).first()
    assert settings is not None
    assert settings.sync_enabled is True
    assert "hubspot" in event.get_plugins()


@pytest.mark.django_db
def test_event_created_skips_hubspot_when_organizer_disabled(organizer):
    from eventyay.base.models import Event

    # OrganizerHubSpotSettings doesn't exist
    event1 = Event.objects.create(
        organizer=organizer,
        name="Test Event 1",
        slug="test-event-1",
        date_from=now(),
        live=False,
    )
    assert HubSpotEventSettings.objects.filter(event=event1).first() is None

    # OrganizerHubSpotSettings exists but disabled
    from hubspot.models import OrganizerHubSpotSettings

    OrganizerHubSpotSettings.objects.create(organizer=organizer, sync_enabled=False)

    event2 = Event.objects.create(
        organizer=organizer,
        name="Test Event 2",
        slug="test-event-2",
        date_from=now(),
        live=False,
    )
    assert HubSpotEventSettings.objects.filter(event=event2).first() is None
