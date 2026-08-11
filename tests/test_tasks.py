from unittest import mock

import pytest
from celery.exceptions import Retry
from django.contrib.contenttypes.models import ContentType
from django_scopes import scopes_disabled
from eventyay.base.models import InvoiceAddress

from hubspot.client import HubSpotPermanentError, HubSpotTransientError
from hubspot.models import (
    HubSpotEventSettings,
    HubSpotFieldMapping,
    HubSpotObjectMapping,
    ObjectTypeMapping,
    SyncLog,
    SyncMode,
    SyncStatus,
)
from hubspot.tasks import (
    _convert_value,
    sync_order_to_hubspot,
)


@pytest.fixture(autouse=True)
def disable_scopes():
    with scopes_disabled():
        yield


def test_convert_value():
    assert _convert_value(None, "text") is None
    assert _convert_value("", "text") is None
    assert _convert_value(123, "text") == "123"

    assert _convert_value("123.45", "number") == 123.45
    assert _convert_value("abc", "number") is None

    assert _convert_value(True, "yes/no") == "true"
    assert _convert_value(False, "yes/no") == "false"
    assert _convert_value("Yes", "yes/no") == "true"
    assert _convert_value("N", "yes/no") == "false"


@pytest.fixture
def mock_event(event):
    HubSpotEventSettings.objects.create(event=event, sync_enabled=True)
    import datetime

    from django.utils.timezone import now

    from hubspot.models import HubSpotOAuthToken

    HubSpotOAuthToken.objects.create(
        event=event,
        access_token="valid_access",
        refresh_token="valid_refresh",
        expires_at=now() + datetime.timedelta(hours=1),
    )
    return event


@pytest.fixture
def object_mapping(mock_event):
    return ObjectTypeMapping.objects.create(
        event=mock_event, eventyay_object_type="order", hubspot_object_type="contacts"
    )


@pytest.mark.django_db
@mock.patch("hubspot.tasks.create_record")
def test_sync_skipped_when_disabled(mock_create, mock_event, object_mapping, order):
    settings = HubSpotEventSettings.objects.get(event=mock_event)
    settings.sync_enabled = False
    settings.save()

    sync_order_to_hubspot(order.id, mock_event.id)

    mock_create.assert_not_called()


@pytest.mark.django_db
@mock.patch("hubspot.tasks.get_hubspot_properties")
@mock.patch("hubspot.tasks.create_record")
def test_sync_order_success(mock_create, mock_get_props, mock_event, object_mapping, order):
    mock_create.return_value = "hub_123"
    mock_get_props.return_value = [{"key": "email", "data_type": "text"}]

    ct = ContentType.objects.get_for_model(order)
    HubSpotFieldMapping.objects.create(
        event=mock_event,
        content_type=ct,
        eventyay_field="email",
        hubspot_object_type="contacts",
        hubspot_property="email",
        sync_mode=SyncMode.IDENTIFIER,
    )

    order.status = "p"
    order.save()
    sync_order_to_hubspot(order.id, mock_event.id)

    mock_create.assert_called_once()
    assert mock_create.call_args[0][2] == {"email": order.email}

    # Verify SyncRecord created
    mapping = HubSpotObjectMapping.objects.get(event=mock_event, object_id=order.id)
    assert mapping.hubspot_object_id == "hub_123"

    log = SyncLog.objects.get(event=mock_event, object_mapping=mapping)
    assert log.status == SyncStatus.SUCCESS


@pytest.mark.django_db
@mock.patch("hubspot.tasks.get_hubspot_properties")
@mock.patch("hubspot.tasks.get_record")
@mock.patch("hubspot.tasks.update_record")
def test_sync_modes(mock_update, mock_get_record, mock_get_props, mock_event, object_mapping, order):
    mock_update.return_value = "hub_123"
    mock_get_record.return_value = {"company": "OldCompany", "phone": ""}

    mock_get_props.return_value = [
        {"key": "email", "data_type": "text"},
        {"key": "amount", "data_type": "number"},
        {"key": "locale", "data_type": "text"},
    ]

    ct = ContentType.objects.get_for_model(order)

    # Existing mapping
    HubSpotObjectMapping.objects.create(
        event=mock_event,
        content_type=ct,
        object_id=order.id,
        hubspot_object_type="contacts",
        hubspot_object_id="hub_123",
    )

    HubSpotFieldMapping.objects.create(
        event=mock_event,
        content_type=ct,
        eventyay_field="email",
        hubspot_object_type="contacts",
        hubspot_property="email",
        sync_mode=SyncMode.IDENTIFIER,
    )
    HubSpotFieldMapping.objects.create(
        event=mock_event,
        content_type=ct,
        eventyay_field="total",
        hubspot_object_type="contacts",
        hubspot_property="amount",
        sync_mode=SyncMode.OVERWRITE,
    )
    HubSpotFieldMapping.objects.create(
        event=mock_event,
        content_type=ct,
        eventyay_field="locale",
        hubspot_object_type="contacts",
        hubspot_property="locale",
        sync_mode=SyncMode.FILL_IF_NEW,
    )

    # Mocking order values
    order.email = "test@example.com"
    order.total = 100.0
    order.locale = "en"
    order.status = "p"
    order.save()

    sync_order_to_hubspot(order.id, mock_event.id)

    mock_update.assert_called_once()
    properties_sent = mock_update.call_args[0][3]

    assert "email" in properties_sent
    assert "amount" in properties_sent
    assert "locale" not in properties_sent  # Skipped because Fill if New and record exists


@pytest.mark.django_db
@mock.patch("hubspot.tasks.get_hubspot_properties")
@mock.patch("hubspot.tasks.get_record")
@mock.patch("hubspot.tasks.update_record")
def test_sync_fill_if_empty(mock_update, mock_get_record, mock_get_props, mock_event, object_mapping, order):
    mock_update.return_value = "hub_123"
    mock_get_record.return_value = {"phone": "", "company": "ExistingCorp"}

    mock_get_props.return_value = [
        {"key": "phone", "data_type": "text"},
        {"key": "company", "data_type": "text"},
    ]

    ct = ContentType.objects.get_for_model(order)
    HubSpotObjectMapping.objects.create(
        event=mock_event,
        content_type=ct,
        object_id=order.id,
        hubspot_object_type="contacts",
        hubspot_object_id="hub_123",
    )

    HubSpotFieldMapping.objects.create(
        event=mock_event,
        content_type=ct,
        eventyay_field="phone",
        hubspot_object_type="contacts",
        hubspot_property="phone",
        sync_mode=SyncMode.FILL_IF_EMPTY,
    )
    HubSpotFieldMapping.objects.create(
        event=mock_event,
        content_type=ct,
        eventyay_field="invoice_company",
        hubspot_object_type="contacts",
        hubspot_property="company",
        sync_mode=SyncMode.FILL_IF_EMPTY,
    )

    order.phone = "12345"
    order.status = "p"
    order.save()

    InvoiceAddress.objects.create(order=order, company="NewCorp")

    HubSpotFieldMapping.objects.filter(hubspot_property="company").update(eventyay_field="event_name")
    order.event.name = "NewEvent"
    order.event.save()

    sync_order_to_hubspot(order.id, mock_event.id)

    properties_sent = mock_update.call_args[0][3]
    assert "phone" in properties_sent  # Was empty, so sent
    assert properties_sent["phone"] == "12345"
    assert "company" not in properties_sent  # Was not empty, so skipped


@pytest.mark.django_db
@mock.patch("hubspot.tasks.get_hubspot_properties")
@mock.patch("hubspot.tasks.create_record")
@mock.patch("hubspot.tasks.sync_order_to_hubspot.retry")
def test_transient_error_retries(mock_retry, mock_create, mock_get_props, mock_event, object_mapping, order):
    mock_retry.side_effect = Retry()
    mock_create.side_effect = HubSpotTransientError("Timeout", retry_after_seconds=10)
    mock_get_props.return_value = [{"key": "email", "data_type": "text"}]

    ct = ContentType.objects.get_for_model(order)

    HubSpotFieldMapping.objects.create(
        event=mock_event,
        content_type=ct,
        eventyay_field="email",
        hubspot_object_type="contacts",
        hubspot_property="email",
        sync_mode=SyncMode.IDENTIFIER,
    )

    order.status = "p"
    order.save()

    with pytest.raises(Retry):
        sync_order_to_hubspot(order.id, mock_event.id)

    mock_retry.assert_called_once()
    assert mock_retry.call_args[1]["countdown"] == 10


@pytest.mark.django_db
@mock.patch("hubspot.tasks.get_hubspot_properties")
@mock.patch("hubspot.tasks.create_record")
def test_permanent_error_no_retry(mock_create, mock_get_props, mock_event, object_mapping, order):
    mock_create.side_effect = HubSpotPermanentError("Invalid data", status_code=400)
    mock_get_props.return_value = [{"key": "email", "data_type": "text"}]

    ct = ContentType.objects.get_for_model(order)

    HubSpotFieldMapping.objects.create(
        event=mock_event,
        content_type=ct,
        eventyay_field="email",
        hubspot_object_type="contacts",
        hubspot_property="email",
        sync_mode=SyncMode.IDENTIFIER,
    )

    order.status = "p"
    order.save()
    sync_order_to_hubspot(order.id, mock_event.id)

    logs = SyncLog.objects.filter(event=mock_event)
    assert logs.count() == 1
    assert logs.first().status == SyncStatus.FAILED


@pytest.mark.django_db
@mock.patch("hubspot.tasks.sync_hubspot_properties")
def test_refresh_hubspot_properties_task_retries_and_error(mock_sync, mock_event):
    from django.core.cache import cache

    from hubspot.services import HubSpotFetchError
    from hubspot.tasks import refresh_hubspot_properties_task

    cache.clear()
    assert refresh_hubspot_properties_task.max_retries == 3

    # Test retry mechanism and lock preservation on failure before max retries
    mock_sync.side_effect = HubSpotFetchError("Rate limited")
    lock_key = f"hubspot_properties_lock_evt_{mock_event.id}_contact"
    error_key = f"hubspot_properties_error_evt_{mock_event.id}_contact"

    cache.set(lock_key, "1")

    with mock.patch.object(refresh_hubspot_properties_task, "retry") as mock_retry:
        mock_retry.side_effect = Exception("RetryCalled")
        with pytest.raises(Exception, match="RetryCalled"):
            refresh_hubspot_properties_task(mock_event.id, "contact")

        # Before reaching max retries, error_key should not be set, and lock_key should still be preserved
        assert cache.get(error_key) is None
        assert cache.get(lock_key) is not None

    # Test max retries exceeded behavior
    cache.set(lock_key, "1")
    with mock.patch.object(refresh_hubspot_properties_task.request, "retries", 3):
        try:
            refresh_hubspot_properties_task(mock_event.id, "contact")
        except Exception:
            pass

        # Error should be set and lock should be released when retries are exhausted
        assert cache.get(error_key) == "Rate limited"
        assert cache.get(lock_key) is None
