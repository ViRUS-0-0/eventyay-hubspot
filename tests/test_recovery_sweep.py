import datetime
from unittest import mock

import pytest
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.utils.timezone import now
from django_scopes import scopes_disabled
from eventyay.base.models import Order

from hubspot.models import (
    HubSpotEventSettings,
    HubSpotFieldMapping,
    HubSpotOAuthToken,
    HubSpotObjectMapping,
    ObjectTypeMapping,
    SyncAction,
    SyncDirection,
    SyncLog,
    SyncStatus,
)
from hubspot.tasks import recovery_sweep_task


@pytest.fixture(autouse=True)
def disable_scopes():
    with scopes_disabled():
        cache.clear()
        yield


@pytest.fixture
def connected_event(event):
    """Event with HubSpot connected, sync enabled, auto-sync enabled."""
    HubSpotOAuthToken.objects.create(
        event=event,
        access_token="valid_access",
        refresh_token="valid_refresh",
        expires_at=now() + datetime.timedelta(hours=1),
    )
    HubSpotEventSettings.objects.create(event=event, sync_enabled=True, auto_sync_enabled=True)
    return event


@pytest.fixture
def order_mapping(connected_event):
    """ObjectTypeMapping for order -> contacts."""
    return ObjectTypeMapping.objects.create(
        event=connected_event,
        eventyay_object_type="order",
        hubspot_object_type="contacts",
    )


@pytest.fixture
def field_mapping(connected_event, order_mapping):
    """A field mapping so orders are considered 'needing sync'."""
    ct = ContentType.objects.get_for_model(Order)
    return HubSpotFieldMapping.objects.create(
        event=connected_event,
        content_type=ct,
        eventyay_field="email",
        hubspot_object_type="contacts",
        hubspot_property="email",
    )


@pytest.fixture
def paid_order(order):
    order.status = Order.STATUS_PAID
    order.save()
    return order


@pytest.mark.django_db
@mock.patch("hubspot.tasks.sync_order_to_hubspot.apply_async")
def test_failed_records_are_requeued(mock_apply, connected_event, order_mapping, field_mapping, paid_order):
    """An order with a FAILED SyncLog gets re-enqueued."""
    ct = ContentType.objects.get_for_model(Order)
    om = HubSpotObjectMapping.objects.create(
        event=connected_event,
        content_type=ct,
        object_id=paid_order.id,
        hubspot_object_type="contacts",
        hubspot_object_id="hs_123",
        last_synced_at=now(),
    )
    SyncLog.objects.create(
        event=connected_event,
        object_mapping=om,
        action=SyncAction.CREATE,
        direction=SyncDirection.PUSH,
        status=SyncStatus.FAILED,
        detail={"error": "Timeout"},
    )

    recovery_sweep_task(connected_event.id)

    mock_apply.assert_called_once_with(args=[paid_order.id, connected_event.id])


@pytest.mark.django_db
@mock.patch("hubspot.tasks.sync_order_to_hubspot.apply_async")
def test_never_synced_orders_are_picked_up(mock_apply, connected_event, order_mapping, field_mapping, paid_order):
    """A paid order with no HubSpotObjectMapping gets enqueued."""
    recovery_sweep_task(connected_event.id)

    mock_apply.assert_called_once_with(args=[paid_order.id, connected_event.id])


@pytest.mark.django_db
@mock.patch("hubspot.tasks.sync_order_to_hubspot.apply_async")
def test_sweep_twice_no_duplicates(mock_apply, connected_event, order_mapping, field_mapping, paid_order):
    """Running the sweep twice only enqueues once (cache lock prevents re-enqueue)."""
    recovery_sweep_task(connected_event.id)
    recovery_sweep_task(connected_event.id)

    mock_apply.assert_called_once_with(args=[paid_order.id, connected_event.id])


@pytest.mark.django_db
@mock.patch("hubspot.tasks.sync_order_to_hubspot.apply_async")
def test_order_already_syncing_is_skipped(mock_apply, connected_event, order_mapping, field_mapping, paid_order):
    """If the recovery lock is already held, the sweep skips that order."""
    cache.set(f"hubspot_recovery_lock_{paid_order.id}", "1", timeout=300)

    recovery_sweep_task(connected_event.id)

    mock_apply.assert_not_called()


@pytest.mark.django_db
@mock.patch("hubspot.tasks.sync_order_to_hubspot.apply_async")
def test_disabled_event_is_skipped(mock_apply, event, paid_order):
    """Events with sync_enabled=False are not swept."""
    HubSpotOAuthToken.objects.create(
        event=event,
        access_token="valid_access",
        refresh_token="valid_refresh",
        expires_at=now() + datetime.timedelta(hours=1),
    )
    HubSpotEventSettings.objects.create(event=event, sync_enabled=False)

    recovery_sweep_task(event.id)

    mock_apply.assert_not_called()


@pytest.mark.django_db
@mock.patch("hubspot.tasks.sync_order_to_hubspot.apply_async")
def test_no_token_event_is_skipped(mock_apply, event, paid_order):
    """Events without an OAuth token are skipped."""
    recovery_sweep_task(event.id)

    mock_apply.assert_not_called()


@pytest.mark.django_db
@mock.patch("hubspot.tasks.sync_order_to_hubspot.apply_async")
def test_auto_sync_disabled_event_is_skipped(mock_apply, event, paid_order):
    """Events with auto_sync_enabled=False are not swept."""
    HubSpotOAuthToken.objects.create(
        event=event,
        access_token="valid_access",
        refresh_token="valid_refresh",
        expires_at=now() + datetime.timedelta(hours=1),
    )
    HubSpotEventSettings.objects.create(event=event, sync_enabled=True, auto_sync_enabled=False)

    recovery_sweep_task(event.id)

    mock_apply.assert_not_called()


@pytest.mark.django_db
@mock.patch("hubspot.tasks.recovery_sweep_task.apply_async")
def test_signal_handler_dispatches_task(mock_apply, connected_event):
    """The signal handler calls recovery_sweep_task.apply_async for connected events."""
    from hubspot.signals import _recovery_sweep_inner

    _recovery_sweep_inner(sender=None)

    mock_apply.assert_called_once_with(args=[connected_event.id])


@pytest.mark.django_db
@mock.patch("hubspot.tasks.sync_order_to_hubspot.apply_async")
def test_already_synced_order_is_not_requeued(mock_apply, connected_event, order_mapping, field_mapping, paid_order):
    """An order that was already successfully synced is not re-enqueued."""
    ct = ContentType.objects.get_for_model(Order)
    om = HubSpotObjectMapping.objects.create(
        event=connected_event,
        content_type=ct,
        object_id=paid_order.id,
        hubspot_object_type="contacts",
        hubspot_object_id="hs_123",
        last_synced_at=now(),
    )
    SyncLog.objects.create(
        event=connected_event,
        object_mapping=om,
        action=SyncAction.CREATE,
        direction=SyncDirection.PUSH,
        status=SyncStatus.SUCCESS,
    )

    recovery_sweep_task(connected_event.id)

    mock_apply.assert_not_called()
