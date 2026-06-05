import pytest
from hubspot.models import (
    HubSpotEventSettings,
    HubSpotFieldMapping,
    HubSpotOAuthToken,
    HubSpotObjectMapping,
    SyncLog,
)


@pytest.mark.django_db
def test_oauth_token_model(event):
    token = HubSpotOAuthToken.objects.create(
        event=event,
        access_token="acc_123",
        refresh_token="ref_123",
        hub_id="hub_1",
    )
    assert token.event == event
    assert str(token) == f"OAuth Token for {event.name}"


@pytest.mark.django_db
def test_event_settings_model(event):
    settings = HubSpotEventSettings.objects.create(
        event=event,
        sync_enabled=True,
    )
    assert settings.sync_enabled is True
    assert str(settings) == f"HubSpot Settings for {event.name}"


@pytest.mark.django_db
def test_object_mapping_model(event):
    mapping = HubSpotObjectMapping.objects.create(
        event=event,
        eventyay_model="order",
        eventyay_id="101",
        hubspot_object_type="deal",
        hubspot_object_id="202",
    )
    assert mapping.eventyay_model == "order"
    assert str(mapping) == "order (101) -> deal (202)"


@pytest.mark.django_db
def test_field_mapping_model(event):
    mapping = HubSpotFieldMapping.objects.create(
        event=event,
        eventyay_model="order",
        eventyay_field="total",
        hubspot_object_type="deal",
        hubspot_property="amount",
    )
    assert mapping.is_active is True
    assert str(mapping) == "order.total -> deal.amount"


@pytest.mark.django_db
def test_sync_log_model(event):
    log = SyncLog.objects.create(
        event=event,
        action="create",
        direction="push",
        status="success",
        detail={"status_code": 200},
    )
    assert log.action == "create"
    assert "create" in str(log)
    assert log.detail["status_code"] == 200
