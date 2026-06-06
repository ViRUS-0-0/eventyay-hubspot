import pytest
from eventyay.base.models import Event, Organizer
from django.utils.timezone import now
from datetime import timedelta


@pytest.fixture
def organizer():
    return Organizer.objects.create(name="Test Organizer", slug="test-org")


@pytest.fixture
def event(organizer):
    return Event.objects.create(
        organizer=organizer,
        name="Test Event",
        slug="test-event",
        date_from=now(),
        date_to=now() + timedelta(days=1),
        currency="USD",
        live=True,
        plugins="hubspot",
    )
