import pytest
from django_scopes import scope

from hubspot.models import (
    OrganizerDefaultObjectTypeMapping,
    OrganizerDefaultFieldMapping,
    HubSpotEventSettings,
    HubSpotFieldMapping,
    ObjectTypeMapping,
    SyncMode,
    HubSpotOAuthToken,
    OrganizerHubSpotOAuthToken,
)
from hubspot.services import (
    apply_default_mappings_to_all_events,
    check_and_clear_mapping_conflict,
)


def _connect_event(event):
    token = HubSpotOAuthToken(event=event, hub_id="123", hub_name="test-hub")
    token.access_token = "acc"
    token.refresh_token = "ref"
    token.save()
    HubSpotEventSettings.objects.create(event=event, sync_enabled=True)


def _connect_organizer(organizer):
    token = OrganizerHubSpotOAuthToken(
        organizer=organizer, hub_id="123", hub_name="test-hub"
    )
    token.access_token = "acc"
    token.refresh_token = "ref"
    token.save()


@pytest.fixture
def org_default_mapping(organizer):
    with scope(organizer=organizer):
        otm = OrganizerDefaultObjectTypeMapping.objects.create(
            organizer=organizer,
            eventyay_object_type="order",
            hubspot_object_type="contacts",
        )
        OrganizerDefaultFieldMapping.objects.create(
            object_type_mapping=otm,
            eventyay_field="email",
            hubspot_property="email",
            sync_mode=SyncMode.IDENTIFIER,
        )
        OrganizerDefaultFieldMapping.objects.create(
            object_type_mapping=otm,
            eventyay_field="total",
            hubspot_property="amount",
            sync_mode=SyncMode.OVERWRITE,
        )
        return otm


@pytest.mark.django_db
def test_apply_defaults_no_existing_mappings(organizer, event, org_default_mapping):
    _connect_event(event)
    apply_default_mappings_to_all_events(organizer)

    with scope(organizer=organizer):
        otm = ObjectTypeMapping.objects.get(event=event)
        assert otm.eventyay_object_type == "order"
        assert otm.hubspot_object_type == "contacts"

        fields = HubSpotFieldMapping.objects.filter(event=event).order_by(
            "eventyay_field"
        )
        assert fields.count() == 2
        assert fields[0].eventyay_field == "email"
        assert fields[0].source == "organizer_default"
        assert fields[1].eventyay_field == "total"
        assert fields[1].source == "organizer_default"

        ev_settings = HubSpotEventSettings.objects.get(event=event)
        assert not ev_settings.has_mapping_conflict


@pytest.mark.django_db
def test_apply_defaults_same_field_conflict(organizer, event, org_default_mapping):
    _connect_event(event)

    with scope(organizer=organizer):
        # Event already maps "email" to something else
        ObjectTypeMapping.objects.create(
            event=event, eventyay_object_type="order", hubspot_object_type="contacts"
        )
        from django.contrib.contenttypes.models import ContentType
        from eventyay.base.models import Order

        HubSpotFieldMapping.objects.create(
            event=event,
            content_type=ContentType.objects.get_for_model(Order),
            eventyay_field="email",
            hubspot_object_type="contacts",
            hubspot_property="alternate_email",
            sync_mode=SyncMode.IDENTIFIER,
            source="custom",
        )

    apply_default_mappings_to_all_events(organizer)

    with scope(organizer=organizer):
        fields = HubSpotFieldMapping.objects.filter(event=event).order_by(
            "eventyay_field"
        )
        assert fields.count() == 3

        email_field = fields.get(eventyay_field="email", source="custom")
        assert email_field.hubspot_property == "alternate_email"  # Kept original
        assert email_field.source == "custom"

        total_field = fields.get(eventyay_field="total")
        assert total_field.source == "organizer_default"

        ev_settings = HubSpotEventSettings.objects.get(event=event)
        assert ev_settings.has_mapping_conflict


@pytest.mark.django_db
def test_conflict_auto_clears_on_delete(organizer, event, org_default_mapping):
    _connect_event(event)
    with scope(organizer=organizer):
        ev_settings = HubSpotEventSettings.objects.get(event=event)
        ev_settings.has_mapping_conflict = True
        ev_settings.save()

        # Assuming the conflict was on 'email', user deletes the 'email' row.
        # Now there are no conflicts.

    check_and_clear_mapping_conflict(event)

    with scope(organizer=organizer):
        ev_settings.refresh_from_db()
        assert not ev_settings.has_mapping_conflict
