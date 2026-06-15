import datetime
from unittest import mock

import pytest
from django.utils.timezone import now
from django_scopes import scope

from hubspot.models import HubSpotOAuthToken
from hubspot.services import get_valid_hubspot_token


@pytest.fixture
def hubspot_token(event):
    with scope(organizer=event.organizer):
        return HubSpotOAuthToken.objects.create(
            event=event,
            access_token="old_access",
            refresh_token="old_refresh",
            expires_at=now() + datetime.timedelta(hours=1),
        )


@pytest.mark.django_db
def test_valid_token_returned_as_is(event, hubspot_token):
    # Token has 1 hour left, should be returned as is
    with scope(organizer=event.organizer):
        token_str = get_valid_hubspot_token(event)
        assert token_str == "old_access"


@pytest.mark.django_db
@mock.patch("hubspot.services.requests.post")
def test_token_expiring_soon_is_refreshed(mock_post, event, hubspot_token):
    # Set expiration to 4 minutes from now
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
    # To test select_for_update we usually need threading or special DB setup
    # But we can at least assert that we are calling select_for_update.
    # A true concurrent test is hard in sqlite but we can mock select_for_update.
    with mock.patch(
        "hubspot.models.HubSpotOAuthToken.objects.select_for_update"
    ) as mock_sfu:
        mock_qs = mock.Mock()
        mock_sfu.return_value = mock_qs
        mock_qs.get.return_value = hubspot_token

        with scope(organizer=event.organizer):
            get_valid_hubspot_token(event)

        mock_sfu.assert_called_once()
