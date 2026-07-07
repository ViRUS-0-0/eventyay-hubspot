import datetime
from django.utils.timezone import now
import pytest
from unittest import mock
from hubspot.models import HubSpotEventSettings
from hubspot.signals import _enqueue_hubspot_sync
from django_scopes import scopes_disabled


@pytest.fixture(autouse=True)
def disable_scopes():
    with scopes_disabled():
        from django.core.cache import cache

        cache.clear()
        yield


@pytest.mark.django_db
@mock.patch("hubspot.signals.sync_order_to_hubspot.apply_async")
def test_enqueue_sync_skipped_if_disabled(mock_apply, event, order):
    # No settings
    _enqueue_hubspot_sync(None, order)
    mock_apply.assert_not_called()

    # Disabled
    HubSpotEventSettings.objects.create(event=event, sync_enabled=False)
    _enqueue_hubspot_sync(None, order)
    mock_apply.assert_not_called()


@pytest.mark.django_db
@mock.patch("hubspot.signals.sync_order_to_hubspot.apply_async")
def test_enqueue_sync_success(
    mock_apply, event, order, django_capture_on_commit_callbacks
):
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
