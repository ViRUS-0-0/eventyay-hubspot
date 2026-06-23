from django.utils.translation import gettext_lazy as _
from eventyay.base.models import Question

QUESTION_TYPE_MAP = {
    Question.TYPE_NUMBER: "number",
    Question.TYPE_BOOLEAN: "yes/no",
    Question.TYPE_DATE: "date",
    Question.TYPE_DATETIME: "date",
    Question.TYPE_TIME: "date",
    Question.TYPE_CHOICE_MULTIPLE: "text",
    Question.TYPE_CHOICE: "text",
    Question.TYPE_STRING: "text",
    Question.TYPE_TEXT: "text",
    Question.TYPE_CHOICE_DROPDOWN: "text",
    Question.TYPE_COUNTRYCODE: "text",
    Question.TYPE_PHONENUMBER: "text",
    Question.TYPE_DESCRIPTION: "text",
    # Question.TYPE_FILE intentionally omitted — file uploads are not syncable
}


def get_available_fields(object_type: str, event=None) -> list[dict]:
    """
    Returns a list of available fields for a given object type ('order' or 'order_position').
    Includes standard fields, invoice address fields (for order), and active event questions (for order_position).
    """
    if object_type == "order":
        return [
            # Standard order fields
            {"key": "code", "label": _("Order code"), "data_type": "text"},
            {"key": "status", "label": _("Order status"), "data_type": "text"},
            {"key": "total", "label": _("Order total"), "data_type": "number"},
            {"key": "datetime", "label": _("Order date and time"), "data_type": "date"},
            {"key": "email", "label": _("Order email"), "data_type": "text"},
            {
                "key": "email_domain",
                "label": _("Order email domain"),
                "data_type": "text",
            },
            {
                "key": "event_and_order_code",
                "label": _("Event and order code"),
                "data_type": "text",
            },
            {
                "key": "payment_datetime",
                "label": _("Payment date and time"),
                "data_type": "date",
            },
            {"key": "locale", "label": _("Order locale"), "data_type": "text"},
            {"key": "order_link", "label": _("Order link"), "data_type": "text"},
            # Invoice fields
            {
                "key": "invoice_name",
                "label": _("Invoice address name"),
                "data_type": "text",
            },
            {
                "key": "invoice_company",
                "label": _("Invoice address company"),
                "data_type": "text",
            },
            {
                "key": "invoice_given_name",
                "label": _("Invoice given name"),
                "data_type": "text",
            },
            {
                "key": "invoice_family_name",
                "label": _("Invoice family name"),
                "data_type": "text",
            },
            {
                "key": "invoice_street",
                "label": _("Invoice street"),
                "data_type": "text",
            },
            {"key": "invoice_zip", "label": _("Invoice zip code"), "data_type": "text"},
            {"key": "invoice_city", "label": _("Invoice city"), "data_type": "text"},
            {
                "key": "invoice_country",
                "label": _("Invoice country"),
                "data_type": "text",
            },
            # Event information
            {"key": "event_slug", "label": _("Event short form"), "data_type": "text"},
            {"key": "event_name", "label": _("Event name"), "data_type": "text"},
            {
                "key": "event_start_date",
                "label": _("Event start date"),
                "data_type": "date",
            },
            {
                "key": "event_end_date",
                "label": _("Event end date"),
                "data_type": "date",
            },
        ]
    elif object_type == "order_position":
        if event is None:
            raise ValueError("event is required when object_type is 'order_position'")

        fields = [
            # Direct fields on OrderPosition (AbstractPosition)
            {
                "key": "attendee_name",
                "label": _("Attendee name"),
                "data_type": "text",
            },  # Extract via: position.attendee_name
            {
                "key": "attendee_given_name",
                "label": _("Attendee given name"),
                "data_type": "text",
            },  # Extract via: position.attendee_name_parts.get('given_name')
            {
                "key": "attendee_family_name",
                "label": _("Attendee family name"),
                "data_type": "text",
            },  # Extract via: position.attendee_name_parts.get('family_name')
            {
                "key": "attendee_email",
                "label": _("Attendee email"),
                "data_type": "text",
            },  # Extract via: position.attendee_email
            {
                "key": "company",
                "label": _("Company"),
                "data_type": "text",
            },  # Extract via: position.company
            {
                "key": "street",
                "label": _("Street"),
                "data_type": "text",
            },  # Extract via: position.street
            {
                "key": "zipcode",
                "label": _("Zipcode"),
                "data_type": "text",
            },  # Extract via: position.zipcode
            {
                "key": "city",
                "label": _("City"),
                "data_type": "text",
            },  # Extract via: position.city
            {
                "key": "country",
                "label": _("Country"),
                "data_type": "text",
            },  # Extract via: str(position.country) if position.country else None
            {
                "key": "state",
                "label": _("State"),
                "data_type": "text",
            },  # Extract via: position.state
            {
                "key": "voucher",
                "label": _("Voucher code"),
                "data_type": "text",
            },  # Extract via: position.voucher.code if position.voucher else None
            {
                "key": "price",
                "label": _("Ticket price"),
                "data_type": "number",
            },  # Extract via: position.price
            {
                "key": "positionid",
                "label": _("Position ID"),
                "data_type": "number",
            },  # Extract via: position.positionid
            {
                "key": "secret",
                "label": _("Ticket secret"),
                "data_type": "text",
            },  # Extract via: position.secret
            # Fields via item/product relationship
            {
                "key": "item_name",
                "label": _("Product name"),
                "data_type": "text",
            },  # Extract via: position.item.name
            {
                "key": "item_admission",
                "label": _("Is admission"),
                "data_type": "yes/no",
            },  # Extract via: position.item.admission
            # Fields via order relationship
            {
                "key": "order_code",
                "label": _("Order code"),
                "data_type": "text",
            },  # Extract via: position.order.code
            {
                "key": "order_email",
                "label": _("Order email"),
                "data_type": "text",
            },  # Extract via: position.order.email
            {
                "key": "order_email_domain",
                "label": _("Order email domain"),
                "data_type": "text",
            },  # Extract via: position.order.email.split('@')[-1] if position.order.email else None
            {
                "key": "order_total",
                "label": _("Order total"),
                "data_type": "number",
            },  # Extract via: position.order.total
            {
                "key": "order_status",
                "label": _("Order status"),
                "data_type": "text",
            },  # Extract via: position.order.status
            {
                "key": "order_datetime",
                "label": _("Order datetime"),
                "data_type": "date",
            },  # Extract via: position.order.datetime
            {
                "key": "order_locale",
                "label": _("Order locale"),
                "data_type": "text",
            },  # Extract via: position.order.locale
        ]

        questions = event.questions.filter(active=True)
        for q in questions:
            if q.type == Question.TYPE_FILE:
                continue

            data_type = QUESTION_TYPE_MAP.get(q.type, "text")

            fields.append(
                {
                    "key": f"question_{q.identifier}",
                    "label": str(q.question),
                    "data_type": data_type,
                }
            )

        return fields

    raise ValueError(
        f"Unknown object_type: {object_type!r}. Expected 'order' or 'order_position'."
    )
