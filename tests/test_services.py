import datetime
from unittest import mock

import pytest
import requests
from django.core.cache import cache
from django.utils.timezone import now
from django_scopes import scope

from hubspot.models import (
    HubSpotEventSettings,
    HubSpotOAuthToken,
    OrganizerHubSpotOAuthToken,
    OrganizerHubSpotSettings,
)
from hubspot.services import (
    HubSpotFetchError,
    get_hubspot_properties,
    get_valid_hubspot_token,
    is_sync_enabled,
    sync_hubspot_properties,
)


@pytest.fixture
def hubspot_token(event):
    with scope(organizer=event.organizer):
        HubSpotEventSettings.objects.create(event=event, sync_enabled=True)
        return HubSpotOAuthToken.objects.create(
            event=event,
            access_token="old_access",
            refresh_token="old_refresh",
            expires_at=now() + datetime.timedelta(hours=1),
        )


@pytest.mark.django_db
def test_valid_token_returned_as_is(event, hubspot_token):
    with scope(organizer=event.organizer):
        token_str = get_valid_hubspot_token(event)
        assert token_str == "old_access"


@pytest.mark.django_db
@mock.patch("hubspot.services.requests.post")
def test_token_expiring_soon_is_refreshed(mock_post, event, hubspot_token):
    with scope(organizer=event.organizer):
        hubspot_token.expires_at = now() + datetime.timedelta(minutes=4)
        hubspot_token.save()

    mock_response = mock.Mock()
    mock_response.ok = True
    mock_response.json.return_value = {
        "access_token": "new_access",
        "refresh_token": "new_refresh",
        "expires_in": 1800,
    }
    mock_post.return_value = mock_response

    token_str = get_valid_hubspot_token(event)

    assert token_str == "new_access"
    mock_post.assert_called_once()

    with scope(organizer=event.organizer):
        hubspot_token.refresh_from_db()
        assert hubspot_token.access_token == "new_access"
        assert hubspot_token.refresh_token == "new_refresh"
        assert hubspot_token.expires_at > now() + datetime.timedelta(minutes=20)


@pytest.mark.django_db
@mock.patch("hubspot.services.requests.post")
def test_concurrent_refresh_attempts(mock_post, event, hubspot_token):
    with mock.patch("hubspot.models.HubSpotOAuthToken.objects.select_for_update") as mock_sfu:
        mock_qs = mock.Mock()
        mock_sfu.return_value = mock_qs
        mock_qs.get.return_value = hubspot_token

        with scope(organizer=event.organizer):
            get_valid_hubspot_token(event)

        mock_sfu.assert_called_once()


@pytest.mark.django_db
@mock.patch("hubspot.tasks.refresh_hubspot_properties_task.apply_async")
@mock.patch("hubspot.services.requests.get")
def test_sync_hubspot_properties_success_and_cache(mock_get, mock_task, event, hubspot_token):
    cache.clear()

    mock_response_1 = mock.Mock()
    mock_response_1.ok = True
    mock_response_1.json.return_value = {
        "results": [
            {"name": "firstname", "label": "First Name", "type": "string"},
            {"name": "age", "label": "Age", "type": "number"},
        ],
        "paging": {"next": {"after": "page2"}},
    }

    mock_response_2 = mock.Mock()
    mock_response_2.ok = True
    mock_response_2.json.return_value = {
        "results": [
            {"name": "createdate", "label": "Create Date", "type": "datetime"},
            {"name": "is_active", "label": "Is Active", "type": "bool"},
        ]
    }
    mock_get.side_effect = [
        mock_response_1,
        mock_response_2,
        mock_response_1,
        mock_response_2,
    ]

    # Test sync_hubspot_properties directly to verify API parsing
    with scope(organizer=event.organizer):
        properties = sync_hubspot_properties(event, "contact")

    assert len(properties) == 4
    assert properties[0] == {
        "key": "firstname",
        "label": "First Name",
        "data_type": "text",
    }
    assert properties[1] == {"key": "age", "label": "Age", "data_type": "number"}
    assert mock_get.call_count == 2

    # Test get_hubspot_properties first-fetch behavior (should fetch synchronously when cold)
    cache.clear()
    with scope(organizer=event.organizer):
        properties2 = get_hubspot_properties(event, "contact")

    assert len(properties2) == 4
    assert mock_get.call_count == 4
    mock_task.assert_not_called()


@pytest.mark.django_db
@mock.patch("hubspot.tasks.refresh_hubspot_properties_task.apply_async")
def test_get_hubspot_properties_ttl_expiry(mock_task, event, hubspot_token):
    cache.clear()

    # Simulate TTL expiry in cache
    data_key = f"hubspot_properties_{event.id}_contact"
    cached_data = {
        "fetched_at": now() - datetime.timedelta(minutes=15),
        "properties": [{"key": "firstname", "label": "First Name", "data_type": "text"}],
    }
    cache.set(data_key, cached_data)

    # Call should trigger celery task and return stale data without hitting API again synchronously
    with scope(organizer=event.organizer):
        properties2 = get_hubspot_properties(event, "contact")

    assert len(properties2) == 1
    mock_task.assert_called_once_with(args=[event.id, "contact"])


@pytest.mark.django_db
def test_sync_hubspot_properties_no_token(event, caplog):
    cache.clear()
    with scope(organizer=event.organizer):
        with pytest.raises(HubSpotFetchError, match="Not connected to HubSpot or token is invalid"):
            sync_hubspot_properties(event, "contact")


@pytest.mark.django_db
@mock.patch("hubspot.services.requests.get")
def test_sync_hubspot_properties_api_failure(mock_get, event, hubspot_token, caplog):
    cache.clear()
    mock_get.side_effect = requests.RequestException("API error")

    with scope(organizer=event.organizer):
        with pytest.raises(HubSpotFetchError, match="Could not connect to HubSpot API"):
            sync_hubspot_properties(event, "contact")


@pytest.mark.django_db
@mock.patch("hubspot.tasks.refresh_hubspot_properties_task.apply_async")
@mock.patch("hubspot.services.requests.get")
def test_get_hubspot_properties_error_suppression(mock_get, mock_task, event, hubspot_token):
    cache.clear()
    error_key = f"hubspot_properties_error_{event.id}_contact"
    cache.set(error_key, "Max retries exceeded")

    # When error_key is set and force_sync is False, get_hubspot_properties should not
    # fetch synchronously or trigger task
    with scope(organizer=event.organizer):
        props = get_hubspot_properties(event, "contact", force_sync=False)

    assert props == []
    mock_task.assert_not_called()
    mock_get.assert_not_called()

    # When force_sync is True on stale cache, error_key is cleared and task is triggered
    data_key = f"hubspot_properties_{event.id}_contact"
    cache.set(
        data_key,
        {
            "fetched_at": now() - datetime.timedelta(minutes=15),
            "properties": [{"key": "firstname", "label": "First Name", "data_type": "text"}],
        },
    )
    with scope(organizer=event.organizer):
        get_hubspot_properties(event, "contact", force_sync=True)

    assert cache.get(error_key) is None
    mock_task.assert_called_once_with(args=[event.id, "contact"])


@pytest.mark.django_db
@mock.patch("hubspot.tasks.refresh_hubspot_properties_task.apply_async")
def test_get_hubspot_properties_auto_sync_rate_limit(mock_task, event, hubspot_token):
    cache.clear()
    # Populate stale cache so background refresh is tested
    data_key = f"hubspot_properties_{event.id}_contact"
    cache.set(
        data_key,
        {
            "fetched_at": now() - datetime.timedelta(minutes=15),
            "properties": [{"key": "firstname", "label": "First Name", "data_type": "text"}],
        },
    )
    with scope(organizer=event.organizer):
        get_hubspot_properties(event, "contact", force_sync=False)

    assert mock_task.call_count == 1

    # Simulate lock expiring or being deleted after task failure/completion while within 30s auto-sync limit
    lock_key = f"hubspot_properties_lock_{event.id}_contact"
    cache.delete(lock_key)

    with scope(organizer=event.organizer):
        get_hubspot_properties(event, "contact", force_sync=False)

    # Should not trigger celery task again because of rate limit key
    assert mock_task.call_count == 1


@pytest.mark.django_db
def test_is_sync_enabled_false_by_default(event):
    with scope(organizer=event.organizer):
        assert is_sync_enabled(event) is False


@pytest.mark.django_db
def test_is_sync_enabled_event_level_no_token(event):
    with scope(organizer=event.organizer):
        HubSpotEventSettings.objects.create(event=event, sync_enabled=True)
        # Even if enabled, without a token it should be false
        assert is_sync_enabled(event) is False


@pytest.mark.django_db
def test_is_sync_enabled_event_level_with_token(event, hubspot_token):
    with scope(organizer=event.organizer):
        # Token exists via the hubspot_token fixture
        assert is_sync_enabled(event) is True


@pytest.mark.django_db
def test_is_sync_enabled_organizer_level_no_token(event):
    with scope(organizer=event.organizer):
        OrganizerHubSpotSettings.objects.create(organizer=event.organizer, sync_enabled=True)
        assert is_sync_enabled(event) is False


@pytest.mark.django_db
def test_is_sync_enabled_organizer_level_with_token(event):
    with scope(organizer=event.organizer):
        OrganizerHubSpotSettings.objects.create(organizer=event.organizer, sync_enabled=True)
        OrganizerHubSpotOAuthToken.objects.create(
            organizer=event.organizer,
            access_token="org_access",
            refresh_token="org_refresh",
            expires_at=now() + datetime.timedelta(hours=1),
        )
        assert is_sync_enabled(event) is True


@pytest.mark.django_db
def test_is_sync_enabled_event_level_disabled_fallback_to_organizer(event):
    with scope(organizer=event.organizer):
        HubSpotEventSettings.objects.create(event=event, sync_enabled=False)
        OrganizerHubSpotSettings.objects.create(organizer=event.organizer, sync_enabled=True)
        OrganizerHubSpotOAuthToken.objects.create(
            organizer=event.organizer,
            access_token="org_access",
            refresh_token="org_refresh",
            expires_at=now() + datetime.timedelta(hours=1),
        )
        assert is_sync_enabled(event) is False
