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
    """If the in-progress lock is already held, the sweep skips that order."""
    cache.set(f"hubspot_sync_in_progress_{paid_order.id}", "1", timeout=600)

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


# --- Bug 1: organizer-connected events ---


@pytest.mark.django_db
@mock.patch("hubspot.tasks.recovery_sweep_task.apply_async")
def test_organizer_connected_event_is_dispatched(mock_apply, event, organizer):
    """Event with no HubSpotOAuthToken but an organizer-level token gets dispatched by the sweep signal."""
    from hubspot.models import OrganizerHubSpotOAuthToken, OrganizerHubSpotSettings
    from hubspot.signals import _recovery_sweep_inner

    OrganizerHubSpotOAuthToken.objects.create(
        organizer=organizer,
        access_token="org_token",
        refresh_token="org_refresh",
        expires_at=now() + datetime.timedelta(hours=1),
    )
    OrganizerHubSpotSettings.objects.create(organizer=organizer, sync_enabled=True)

    _recovery_sweep_inner(sender=None)

    mock_apply.assert_called_once_with(args=[event.id])


@pytest.mark.django_db
@mock.patch("hubspot.tasks.recovery_sweep_task.apply_async")
def test_event_only_token_still_dispatched(mock_apply, connected_event):
    """Event with a direct HubSpotOAuthToken (original behavior) still gets dispatched."""
    from hubspot.signals import _recovery_sweep_inner

    _recovery_sweep_inner(sender=None)

    mock_apply.assert_called_once_with(args=[connected_event.id])


# --- Bug 2: in-progress lock lifecycle ---


@pytest.mark.django_db
@mock.patch("hubspot.tasks.sync_order_to_hubspot.apply_async")
def test_in_progress_lock_blocks_sweep(mock_apply, connected_event, order_mapping, field_mapping, paid_order):
    """Sweep skips an order whose hubspot_sync_in_progress_* lock is held."""
    cache.set(f"hubspot_sync_in_progress_{paid_order.id}", "1", timeout=600)

    recovery_sweep_task(connected_event.id)

    mock_apply.assert_not_called()


@pytest.mark.django_db
@mock.patch("hubspot.tasks._sync_single_object")
def test_in_progress_lock_released_after_success(mock_sync, connected_event, order_mapping, paid_order):
    """In-progress lock is deleted when sync_order_to_hubspot completes successfully."""
    mock_sync.return_value = None  # no-op sync

    from hubspot.tasks import sync_order_to_hubspot

    # Run the task directly (not via celery)
    sync_order_to_hubspot(paid_order.id, connected_event.id)

    assert cache.get(f"hubspot_sync_in_progress_{paid_order.id}") is None


@pytest.mark.django_db
@mock.patch("hubspot.tasks._sync_single_object")
def test_in_progress_lock_held_during_retry(mock_sync, connected_event, order_mapping, paid_order):
    """In-progress lock is NOT released when the task calls self.retry() (still in-flight)."""
    from hubspot.client import HubSpotTransientError
    from hubspot.tasks import sync_order_to_hubspot

    mock_sync.side_effect = HubSpotTransientError("transient")

    # Catch the Retry exception that celery raises internally
    try:
        sync_order_to_hubspot(paid_order.id, connected_event.id)
    except Exception:
        pass  # celery raises Retry; we just verify the lock state below

    # Lock must still be set — task is retrying, not done
    assert cache.get(f"hubspot_sync_in_progress_{paid_order.id}") == "1"


@pytest.mark.django_db
@mock.patch("hubspot.tasks._sync_single_object")
def test_in_progress_lock_released_after_permanent_failure(mock_sync, connected_event, order_mapping, paid_order):
    """In-progress lock is released even after a permanent failure (non-retry exit)."""
    from hubspot.client import HubSpotPermanentError
    from hubspot.tasks import sync_order_to_hubspot

    mock_sync.side_effect = HubSpotPermanentError("permanent")

    # In real execution _sync_single_object catches HubSpotPermanentError internally;
    # here the mock raises it directly, so it propagates — but the finally still fires.
    try:
        sync_order_to_hubspot(paid_order.id, connected_event.id)
    except HubSpotPermanentError:
        pass

    assert cache.get(f"hubspot_sync_in_progress_{paid_order.id}") is None


# --- Bug 3: FAILED → SUCCESS regression ---


@pytest.mark.django_db
@mock.patch("hubspot.tasks.sync_order_to_hubspot.apply_async")
def test_failed_then_succeeded_order_not_requeued(
    mock_apply, connected_event, order_mapping, field_mapping, paid_order
):
    """Order with a FAILED log followed by a later SUCCESS log is NOT re-enqueued."""
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
    # Later successful retry — this should resolve the failure
    SyncLog.objects.create(
        event=connected_event,
        object_mapping=om,
        action=SyncAction.UPDATE,
        direction=SyncDirection.PUSH,
        status=SyncStatus.SUCCESS,
    )

    recovery_sweep_task(connected_event.id)

    mock_apply.assert_not_called()


# --- Cap behavior ---


@pytest.mark.django_db
@mock.patch("hubspot.tasks.sync_order_to_hubspot.apply_async")
def test_cap_defers_excess_orders(mock_apply, connected_event, order_mapping, field_mapping):
    """Orders beyond RECOVERY_SWEEP_MAX_ORDERS=500 are deferred, not dropped."""
    # Create 502 paid orders with no mapping (never synced)
    orders = [
        Order(
            event=connected_event,
            code=f"CAP{i:04d}",
            status=Order.STATUS_PAID,
            email=f"cap{i}@test.com",
            total=10.00,
            locale="en",
            datetime=now(),
            expires=now() + datetime.timedelta(days=30),
        )
        for i in range(502)
    ]
    Order.objects.bulk_create(orders)

    recovery_sweep_task(connected_event.id)

    assert mock_apply.call_count == 500
