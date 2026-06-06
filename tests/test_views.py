import pytest
from django.urls import reverse
from eventyay.base.models import Team, User


@pytest.fixture
def user():
    return User.objects.create_user("dummy@dummy.dummy", "dummy")


@pytest.fixture
def logged_in_client(client, user):
    client.force_login(user)
    return client


@pytest.fixture
def logged_in_organizer_client(client, user, organizer, event):
    team = Team.objects.create(
        organizer=organizer,
        name="Test Team",
        can_change_event_settings=True,
        all_events=True,
    )
    team.members.add(user)
    client.force_login(user)
    return client


@pytest.mark.django_db
def test_hubspot_settings_view_logged_out(client, organizer, event, settings):
    settings.SITE_URL = "https://testserver"
    url = reverse(
        "plugins:hubspot:hubspot",
        kwargs={"organizer": organizer.slug, "event": event.slug},
    )
    response = client.get(url)
    assert response.status_code == 302
    assert "login" in response.url


@pytest.mark.django_db
def test_hubspot_settings_view_wrong_organizer(
    logged_in_client, organizer, event, settings
):
    settings.SITE_URL = "https://testserver"
    url = reverse(
        "plugins:hubspot:hubspot",
        kwargs={"organizer": organizer.slug, "event": event.slug},
    )
    response = logged_in_client.get(url)
    assert response.status_code in [403, 404]


@pytest.mark.django_db
def test_hubspot_settings_view_correct_organizer(
    logged_in_organizer_client, organizer, event, settings
):
    settings.SITE_URL = "https://testserver"
    url = reverse(
        "plugins:hubspot:hubspot",
        kwargs={"organizer": organizer.slug, "event": event.slug},
    )
    response = logged_in_organizer_client.get(url)
    assert response.status_code == 200
