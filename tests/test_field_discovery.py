import pytest
from eventyay.base.models import Question

from django_scopes import scope
from hubspot.field_discovery import get_available_fields


@pytest.mark.django_db
def test_get_available_fields_order():
    fields = get_available_fields("order")

    # Check that we get a non-empty list
    assert isinstance(fields, list)
    assert len(fields) > 0

    # Extract keys for easy checking
    keys = [f["key"] for f in fields]

    # Standard fields
    assert "code" in keys
    assert "status" in keys
    assert "total" in keys
    assert "datetime" in keys
    assert "email" in keys
    assert "email_domain" in keys
    assert "event_and_order_code" in keys
    assert "payment_datetime" in keys
    assert "locale" in keys
    assert "order_link" in keys

    # Invoice address fields
    assert "invoice_name" in keys
    assert "invoice_company" in keys
    assert "invoice_given_name" in keys
    assert "invoice_family_name" in keys
    assert "invoice_street" in keys
    assert "invoice_zip" in keys
    assert "invoice_city" in keys
    assert "invoice_country" in keys

    # Event fields
    assert "event_slug" in keys
    assert "event_name" in keys

    # Validate structure
    for field in fields:
        assert "key" in field
        assert "label" in field
        assert "data_type" in field
        assert field["key"]
        assert field["label"]
        assert field["data_type"] in ("text", "number", "date", "yes/no")


@pytest.mark.django_db
def test_get_available_fields_order_position_no_event():
    with pytest.raises(
        ValueError, match="event is required when object_type is 'order_position'"
    ):
        get_available_fields("order_position")


@pytest.mark.django_db
def test_get_available_fields_order_position_empty_event(event):
    # Event without any questions defined
    with scope(organizer=event.organizer):
        fields = get_available_fields("order_position", event=event)

    # Base fields are 38, and no question fields are appended
    assert len(fields) == 38
    question_fields = [f for f in fields if f["key"].startswith("question_")]
    assert len(question_fields) == 0


@pytest.mark.django_db
def test_get_available_fields_order_position_with_event(event):
    with scope(organizer=event.organizer):
        # Create some questions for the event
        Question.objects.create(
            event=event,
            question="What is your age?",
            type="N",
            active=True,
        )
        Question.objects.create(
            event=event,
            question="Do you like Python?",
            type="B",
            active=True,
        )
        Question.objects.create(
            event=event,
            question="When is your birthday?",
            type="D",
            active=True,
        )
        Question.objects.create(
            event=event,
            question="What is your hobby?",
            type="S",
            active=True,
        )
        # Create an inactive question, should not be included
        Question.objects.create(
            event=event,
            question="Inactive question",
            type="S",
            active=False,
        )
        # File upload question, should not be included
        Question.objects.create(
            event=event,
            question="Upload file",
            type="F",
            active=True,
        )
        # Multiple choice question, mapped to text
        Question.objects.create(
            event=event,
            question="Multiple choice",
            type="M",
            active=True,
        )

        fields = get_available_fields("order_position", event=event)

    # Should have 38 base fields + 5 active questions (N, B, D, S, M)
    assert len(fields) == 43

    keys = [f["key"] for f in fields]
    assert "attendee_name" in keys
    assert "attendee_email" in keys
    assert "company" in keys
    assert "price" in keys
    assert "order_code" in keys
    assert "item_name" in keys

    # Find question fields
    question_fields = [f for f in fields if f["key"].startswith("question_")]
    assert len(question_fields) == 5

    # Check data types mapping
    types_found = {f["data_type"] for f in question_fields}
    assert "number" in types_found
    assert "yes/no" in types_found
    assert "date" in types_found
    assert "text" in types_found

    # Validate structure of all fields
    for field in fields:
        assert "key" in field
        assert "label" in field
        assert "data_type" in field
        assert field["key"]
        assert field["label"]
        assert field["data_type"] in ("text", "number", "date", "yes/no")


def test_get_available_fields_invalid_type():
    with pytest.raises(ValueError, match="Unknown object_type: 'invalid_type'"):
        get_available_fields("invalid_type")
