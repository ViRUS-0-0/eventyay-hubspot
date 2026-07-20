import datetime
from django.utils.timezone import now
import pytest
from unittest import mock
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django_scopes import scopes_disabled

from eventyay.base.models import Order
from hubspot.models import (
    HubSpotEventSettings,
    HubSpotOAuthToken,
    HubSpotObjectMapping,
    SyncLog,
    SyncStatus,
    SyncAction,
    SyncDirection,
)
from hubspot.signals import control_order_info


@pytest.fixture(autouse=True)
def disable_scopes():
    with scopes_disabled():
        yield


@pytest.mark.django_db
def test_order_info_not_connected(client, event, order, organizer):
    class DummyRequest:
        def __init__(self):
            self.user = mock.Mock()
            self.user.has_event_permission.return_value = True
            self.event = event
            self.organizer = organizer
            self.META = {}
            self.resolver_match = mock.Mock()
            self.resolver_match.namespaces = []
            self.path = ""
            self.path_info = ""

    req = DummyRequest()
    html = control_order_info(event, req, order)

    assert "HubSpot is not connected for this event." in html
    assert "Not synced yet" in html
    assert "disabled" in html


@pytest.mark.django_db
def test_order_info_synced(client, event, order, organizer):
    HubSpotEventSettings.objects.create(event=event, sync_enabled=True)
    HubSpotOAuthToken.objects.create(
        event=event,
        access_token="acc",
        refresh_token="ref",
        expires_at=now() + datetime.timedelta(days=1),
    )
    mapping = HubSpotObjectMapping.objects.create(
        event=event,
        content_type=ContentType.objects.get_for_model(Order),
        object_id=order.id,
        hubspot_object_type="contacts",
        hubspot_object_id="123",
        last_synced_at=now(),
    )
    SyncLog.objects.create(
        event=event,
        object_mapping=mapping,
        action=SyncAction.CREATE,
        direction=SyncDirection.PUSH,
        status=SyncStatus.SUCCESS,
    )

    class DummyRequest:
        def __init__(self):
            self.user = mock.Mock()
            self.user.has_event_permission.return_value = True
            self.event = event
            self.organizer = organizer
            self.META = {}
            self.resolver_match = mock.Mock()
            self.resolver_match.namespaces = []
            self.path = ""
            self.path_info = ""

    req = DummyRequest()
    html = control_order_info(event, req, order)

    assert "Synced" in html
    assert "HubSpot is not connected" not in html
    assert 'class="btn btn-primary sync-now-btn"' in html


@pytest.mark.django_db
def test_order_info_failed(client, event, order, organizer):
    HubSpotEventSettings.objects.create(event=event, sync_enabled=True)
    HubSpotOAuthToken.objects.create(
        event=event,
        access_token="acc",
        refresh_token="ref",
        expires_at=now() + datetime.timedelta(days=1),
    )
    mapping = HubSpotObjectMapping.objects.create(
        event=event,
        content_type=ContentType.objects.get_for_model(Order),
        object_id=order.id,
        hubspot_object_type="contacts",
        hubspot_object_id="123",
    )
    SyncLog.objects.create(
        event=event,
        object_mapping=mapping,
        action=SyncAction.CREATE,
        direction=SyncDirection.PUSH,
        status=SyncStatus.FAILED,
    )

    class DummyRequest:
        def __init__(self):
            self.user = mock.Mock()
            self.user.has_event_permission.return_value = True
            self.event = event
            self.organizer = organizer
            self.META = {}
            self.resolver_match = mock.Mock()
            self.resolver_match.namespaces = []
            self.path = ""
            self.path_info = ""

    req = DummyRequest()
    html = control_order_info(event, req, order)

    assert "Failed" in html


@pytest.mark.django_db
def test_order_info_pending_no_mapping(client, event, order, organizer):
    HubSpotEventSettings.objects.create(event=event, sync_enabled=True)
    HubSpotOAuthToken.objects.create(
        event=event,
        access_token="acc",
        refresh_token="ref",
        expires_at=now() + datetime.timedelta(days=1),
    )
    SyncLog.objects.create(
        event=event,
        action=SyncAction.CREATE,
        direction=SyncDirection.PUSH,
        status=SyncStatus.PENDING,
        detail={
            "message": f"Auto-sync disabled, sync pending for order {order.code}",
            "order_code": order.code,
        },
    )

    class DummyRequest:
        def __init__(self):
            self.user = mock.Mock()
            self.user.has_event_permission.return_value = True
            self.event = event
            self.organizer = organizer
            self.META = {}
            self.resolver_match = mock.Mock()
            self.resolver_match.namespaces = []
            self.path = ""
            self.path_info = ""

    req = DummyRequest()
    html = control_order_info(event, req, order)

    assert "Waiting to sync" in html


@pytest.mark.django_db
@mock.patch("hubspot.views.sync_order_to_hubspot.apply_async")
def test_sync_now_view(
    mock_apply, logged_in_organizer_client, event, order, organizer, settings
):
    settings.SITE_URL = "https://testserver"

    order.status = Order.STATUS_PAID
    order.save()

    url = reverse(
        "plugins:hubspot:sync_order",
        kwargs={"organizer": organizer.slug, "event": event.slug, "order": order.code},
    )

    response = logged_in_organizer_client.post(url)
    assert response.status_code == 302
    assert response.url == reverse(
        "control:event.order",
        kwargs={"organizer": organizer.slug, "event": event.slug, "code": order.code},
    )

    mock_apply.assert_called_once_with(args=[order.id, event.id])
