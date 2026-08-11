import pytest
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse
from django.utils.timezone import now
from django_scopes import scope
from eventyay.base.models import Order

from hubspot.models import (
    EventyayObjectType,
    HubSpotEventSettings,
    HubSpotFieldMapping,
    HubSpotOAuthToken,
    HubSpotObjectMapping,
    HubSpotObjectType,
    ObjectTypeMapping,
    SyncAction,
    SyncDirection,
    SyncLog,
    SyncStatus,
)


@pytest.fixture
def setup_hubspot(event):
    with scope(organizer=event.organizer):
        HubSpotOAuthToken.objects.create(
            event=event,
            access_token="test_token",
            hub_id="12345",
            hub_name="Test Hub",
        )
        HubSpotEventSettings.objects.create(event=event, sync_enabled=True)
        mapping = ObjectTypeMapping.objects.create(
            event=event,
            eventyay_object_type=EventyayObjectType.ORDER,
            hubspot_object_type=HubSpotObjectType.CONTACTS,
        )
        HubSpotFieldMapping.objects.create(
            event=event,
            content_type=ContentType.objects.get_for_model(Order),
            hubspot_object_type=mapping.hubspot_object_type,
            eventyay_field="code",
            hubspot_property="firstname",
        )
        return mapping


@pytest.mark.django_db
def test_sync_status_banner_pending_count(logged_in_organizer_client, event, order, setup_hubspot, settings):
    with scope(organizer=event.organizer):
        order.status = Order.STATUS_PAID
        order.save()
    settings.SITE_URL = "https://testserver"
    url = reverse(
        "plugins:hubspot:hubspot",
        kwargs={"organizer": event.organizer.slug, "event": event.slug},
    )
    response = logged_in_organizer_client.get(url)
    assert response.status_code == 200
    assert response.context["pending_count"] == 1
    assert response.context["failed_count"] == 0


@pytest.mark.django_db
def test_sync_status_banner_failed_count(logged_in_organizer_client, event, order, setup_hubspot, settings):
    with scope(organizer=event.organizer):
        order.status = Order.STATUS_PAID
        order.save()
    settings.SITE_URL = "https://testserver"
    order_ct = ContentType.objects.get_for_model(Order)
    with scope(organizer=event.organizer):
        om = HubSpotObjectMapping.objects.create(
            event=event,
            content_type=order_ct,
            object_id=order.id,
            hubspot_object_type=setup_hubspot.hubspot_object_type,
            hubspot_object_id="hs_123",
            last_synced_at=now(),
        )
        SyncLog.objects.create(
            event=event,
            object_mapping=om,
            action=SyncAction.CREATE,
            direction=SyncDirection.PUSH,
            status=SyncStatus.FAILED,
            detail={"error": "Test error"},
        )

    url = reverse(
        "plugins:hubspot:hubspot",
        kwargs={"organizer": event.organizer.slug, "event": event.slug},
    )
    response = logged_in_organizer_client.get(url)
    assert response.status_code == 200
    assert response.context["pending_count"] == 0
    assert response.context["failed_count"] == 1
    assert b"1 order failed to sync to HubSpot." in response.content


@pytest.mark.django_db
def test_sync_problems_list_view(logged_in_organizer_client, event, order, setup_hubspot, settings):
    with scope(organizer=event.organizer):
        order.status = Order.STATUS_PAID
        order.save()
    settings.SITE_URL = "https://testserver"
    url = reverse(
        "plugins:hubspot:sync_problems",
        kwargs={"organizer": event.organizer.slug, "event": event.slug},
    )
    response = logged_in_organizer_client.get(url)
    assert response.status_code == 200
    records = response.context["records"]
    assert len(records) == 1
    assert records[0]["status"] == "pending"
    assert records[0]["code"] == order.code


@pytest.mark.django_db
def test_dismiss_sync_record(logged_in_organizer_client, event, order, setup_hubspot, settings):
    with scope(organizer=event.organizer):
        order.status = Order.STATUS_PAID
        order.save()
    settings.SITE_URL = "https://testserver"
    order_ct = ContentType.objects.get_for_model(Order)
    with scope(organizer=event.organizer):
        om = HubSpotObjectMapping.objects.create(
            event=event,
            content_type=order_ct,
            object_id=order.id,
            hubspot_object_type=setup_hubspot.hubspot_object_type,
            hubspot_object_id="hs_123",
            last_synced_at=now(),
        )
        failed_log = SyncLog.objects.create(
            event=event,
            object_mapping=om,
            action=SyncAction.CREATE,
            direction=SyncDirection.PUSH,
            status=SyncStatus.FAILED,
            detail={"error": "Test error"},
        )

    dismiss_url = reverse(
        "plugins:hubspot:sync_dismiss",
        kwargs={
            "organizer": event.organizer.slug,
            "event": event.slug,
            "log_id": failed_log.id,
        },
    )
    response = logged_in_organizer_client.post(dismiss_url)
    assert response.status_code == 302

    with scope(organizer=event.organizer):
        dismiss_log = SyncLog.objects.filter(event=event, object_mapping=om, action=SyncAction.DISMISS).first()
        assert dismiss_log is not None
        assert dismiss_log.status == SyncStatus.SUCCESS

    settings_url = reverse(
        "plugins:hubspot:hubspot",
        kwargs={"organizer": event.organizer.slug, "event": event.slug},
    )
    settings_response = logged_in_organizer_client.get(settings_url)
    assert settings_response.context["failed_count"] == 0
