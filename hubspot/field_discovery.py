from django.utils.translation import gettext_lazy as _
from eventyay.base.models import Question

QUESTION_TYPE_MAP = {
    Question.TYPE_NUMBER: "number",
    Question.TYPE_BOOLEAN: "yes/no",
    Question.TYPE_DATE: "date",
    Question.TYPE_DATETIME: "date",
    Question.TYPE_TIME: "text",
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
            {
                "key": "code",
                "label": _("Order code"),
                "data_type": "text",
                "category": _("Order details"),
            },
            {
                "key": "status",
                "label": _("Order status"),
                "data_type": "text",
                "category": _("Order details"),
            },
            {
                "key": "total",
                "label": _("Order total"),
                "data_type": "number",
                "category": _("Order details"),
            },
            {
                "key": "datetime",
                "label": _("Order date and time"),
                "data_type": "date",
                "category": _("Order details"),
            },
            {
                "key": "email",
                "label": _("Order email"),
                "data_type": "text",
                "category": _("Order details"),
            },
            {
                "key": "email_domain",
                "label": _("Order email domain"),
                "data_type": "text",
                "category": _("Order details"),
            },
            {
                "key": "event_and_order_code",
                "label": _("Event and order code"),
                "data_type": "text",
                "category": _("Order details"),
            },
            {
                "key": "payment_datetime",
                "label": _("Payment date and time"),
                "data_type": "date",
                "category": _("Order details"),
            },
            {
                "key": "locale",
                "label": _("Order locale"),
                "data_type": "text",
                "category": _("Order details"),
            },
            {
                "key": "order_link",
                "label": _("Order link"),
                "data_type": "text",
                "category": _("Order details"),
            },
            {
                "key": "phone",
                "label": _("Order phone"),
                "data_type": "text",
                "category": _("Order details"),
            },
            {
                "key": "comment",
                "label": _("Order comment"),
                "data_type": "text",
                "category": _("Order details"),
            },
            {
                "key": "testmode",
                "label": _("Is test mode"),
                "data_type": "yes/no",
                "category": _("Order details"),
            },
            # Invoice fields
            {
                "key": "invoice_name",
                "label": _("Invoice address name"),
                "data_type": "text",
                "category": _("Invoice details"),
            },
            {
                "key": "invoice_company",
                "label": _("Invoice address company"),
                "data_type": "text",
                "category": _("Invoice details"),
            },
            {
                "key": "invoice_given_name",
                "label": _("Invoice given name"),
                "data_type": "text",
                "category": _("Invoice details"),
            },
            {
                "key": "invoice_family_name",
                "label": _("Invoice family name"),
                "data_type": "text",
                "category": _("Invoice details"),
            },
            {
                "key": "invoice_street",
                "label": _("Invoice street"),
                "data_type": "text",
                "category": _("Invoice details"),
            },
            {
                "key": "invoice_zip",
                "label": _("Invoice zip code"),
                "data_type": "text",
                "category": _("Invoice details"),
            },
            {
                "key": "invoice_city",
                "label": _("Invoice city"),
                "data_type": "text",
                "category": _("Invoice details"),
            },
            {
                "key": "invoice_country",
                "label": _("Invoice country"),
                "data_type": "text",
                "category": _("Invoice details"),
            },
            {
                "key": "invoice_state",
                "label": _("Invoice state"),
                "data_type": "text",
                "category": _("Invoice details"),
            },
            {
                "key": "invoice_vat_id",
                "label": _("Invoice VAT ID"),
                "data_type": "text",
                "category": _("Invoice details"),
            },
            {
                "key": "invoice_is_business",
                "label": _("Invoice is business"),
                "data_type": "yes/no",
                "category": _("Invoice details"),
            },
            # Event information
            {
                "key": "event_slug",
                "label": _("Event short form"),
                "data_type": "text",
                "category": _("Event information"),
            },
            {
                "key": "event_name",
                "label": _("Event name"),
                "data_type": "text",
                "category": _("Event information"),
            },
            {
                "key": "event_start_date",
                "label": _("Event start date"),
                "data_type": "date",
                "category": _("Event information"),
            },
            {
                "key": "event_end_date",
                "label": _("Event end date"),
                "data_type": "date",
                "category": _("Event information"),
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
                "category": _("Attendee details"),
            },  # Extract via: position.attendee_name
            {
                "key": "attendee_given_name",
                "label": _("Attendee given name"),
                "data_type": "text",
                "category": _("Attendee details"),
            },  # Extract via: position.attendee_name_parts.get('given_name')
            {
                "key": "attendee_family_name",
                "label": _("Attendee family name"),
                "data_type": "text",
                "category": _("Attendee details"),
            },  # Extract via: position.attendee_name_parts.get('family_name')
            {
                "key": "attendee_email",
                "label": _("Attendee email"),
                "data_type": "text",
                "category": _("Attendee details"),
            },  # Extract via: position.attendee_email
            {
                "key": "company",
                "label": _("Company"),
                "data_type": "text",
                "category": _("Attendee details"),
            },  # Extract via: position.company
            {
                "key": "job_title",
                "label": _("Job title"),
                "data_type": "text",
                "category": _("Attendee details"),
            },  # Extract via: position.job_title
            {
                "key": "street",
                "label": _("Street"),
                "data_type": "text",
                "category": _("Attendee details"),
            },  # Extract via: position.street
            {
                "key": "zipcode",
                "label": _("Zipcode"),
                "data_type": "text",
                "category": _("Attendee details"),
            },  # Extract via: position.zipcode
            {
                "key": "city",
                "label": _("City"),
                "data_type": "text",
                "category": _("Attendee details"),
            },  # Extract via: position.city
            {
                "key": "country",
                "label": _("Country"),
                "data_type": "text",
                "category": _("Attendee details"),
            },  # Extract via: str(position.country) if position.country else None
            {
                "key": "state",
                "label": _("State"),
                "data_type": "text",
                "category": _("Attendee details"),
            },  # Extract via: position.state
            {
                "key": "voucher",
                "label": _("Voucher code"),
                "data_type": "text",
                "category": _("Ticket details"),
            },  # Extract via: position.voucher.code if position.voucher else None
            {
                "key": "price",
                "label": _("Ticket price"),
                "data_type": "number",
                "category": _("Ticket details"),
            },  # Extract via: position.price
            {
                "key": "positionid",
                "label": _("Position ID"),
                "data_type": "number",
                "category": _("Ticket details"),
            },  # Extract via: position.positionid
            {
                "key": "secret",
                "label": _("Ticket secret"),
                "data_type": "text",
                "category": _("Ticket details"),
            },  # Extract via: position.secret
            # Fields via item/product relationship
            {
                "key": "item_name",
                "label": _("Product name"),
                "data_type": "text",
                "category": _("Ticket details"),
            },  # Extract via: position.item.name
            {
                "key": "item_admission",
                "label": _("Is admission"),
                "data_type": "yes/no",
                "category": _("Ticket details"),
            },  # Extract via: position.item.admission
            # Fields via order relationship
            {
                "key": "order_code",
                "label": _("Order code"),
                "data_type": "text",
                "category": _("Order details"),
            },  # Extract via: position.order.code
            {
                "key": "order_email",
                "label": _("Order email"),
                "data_type": "text",
                "category": _("Order details"),
            },  # Extract via: position.order.email
            {
                "key": "order_email_domain",
                "label": _("Order email domain"),
                "data_type": "text",
                "category": _("Order details"),
            },  # Extract via: position.order.email.split('@')[-1] if position.order.email else None
            {
                "key": "order_total",
                "label": _("Order total"),
                "data_type": "number",
                "category": _("Order details"),
            },  # Extract via: position.order.total
            {
                "key": "order_status",
                "label": _("Order status"),
                "data_type": "text",
                "category": _("Order details"),
            },  # Extract via: position.order.status
            {
                "key": "order_datetime",
                "label": _("Order datetime"),
                "data_type": "date",
                "category": _("Order details"),
            },  # Extract via: position.order.datetime
            {
                "key": "order_locale",
                "label": _("Order locale"),
                "data_type": "text",
                "category": _("Order details"),
            },  # Extract via: position.order.locale
            {
                "key": "order_phone",
                "label": _("Order phone"),
                "data_type": "text",
                "category": _("Order details"),
            },  # Extract via: position.order.phone
            {
                "key": "order_comment",
                "label": _("Order comment"),
                "data_type": "text",
                "category": _("Order details"),
            },  # Extract via: position.order.comment
            # Invoice fields via order relationship
            {
                "key": "invoice_name",
                "label": _("Invoice address name"),
                "data_type": "text",
                "category": _("Invoice details"),
            },  # Extract via: position.order.invoice_address.name
            {
                "key": "invoice_company",
                "label": _("Invoice address company"),
                "data_type": "text",
                "category": _("Invoice details"),
            },  # Extract via: position.order.invoice_address.company
            {
                "key": "invoice_street",
                "label": _("Invoice street"),
                "data_type": "text",
                "category": _("Invoice details"),
            },  # Extract via: position.order.invoice_address.street
            {
                "key": "invoice_zip",
                "label": _("Invoice zip code"),
                "data_type": "text",
                "category": _("Invoice details"),
            },  # Extract via: position.order.invoice_address.zipcode
            {
                "key": "invoice_city",
                "label": _("Invoice city"),
                "data_type": "text",
                "category": _("Invoice details"),
            },  # Extract via: position.order.invoice_address.city
            {
                "key": "invoice_country",
                "label": _("Invoice country"),
                "data_type": "text",
                "category": _("Invoice details"),
            },  # Extract via: position.order.invoice_address.country
            {
                "key": "invoice_state",
                "label": _("Invoice state"),
                "data_type": "text",
                "category": _("Invoice details"),
            },  # Extract via: position.order.invoice_address.state
            {
                "key": "invoice_vat_id",
                "label": _("Invoice VAT ID"),
                "data_type": "text",
                "category": _("Invoice details"),
            },  # Extract via: position.order.invoice_address.vat_id
            # Event information
            {
                "key": "event_slug",
                "label": _("Event short form"),
                "data_type": "text",
                "category": _("Event information"),
            },
            {
                "key": "event_name",
                "label": _("Event name"),
                "data_type": "text",
                "category": _("Event information"),
            },
            {
                "key": "event_start_date",
                "label": _("Event start date"),
                "data_type": "date",
                "category": _("Event information"),
            },
            {
                "key": "event_end_date",
                "label": _("Event end date"),
                "data_type": "date",
                "category": _("Event information"),
            },
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
                    "category": _("Questions"),
                }
            )

        return fields

    raise ValueError(
        f"Unknown object_type: {object_type!r}. Expected 'order' or 'order_position'."
    )
