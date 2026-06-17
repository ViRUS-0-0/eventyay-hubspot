from django.utils.translation import gettext_lazy as _

QUESTION_TYPE_MAP = {
    "N": "number",
    "B": "yes/no",
    "D": "date",
    "W": "date",
    "H": "date",
    "M": "text",
    "C": "text",
    # "F" intentionally omitted — file uploads are not syncable
}


def get_available_fields(object_type: str, event=None) -> list[dict]:
    """
    Returns a list of available fields for a given object type ('order' or 'order_position').
    Includes standard fields, invoice address fields (for order), and active event questions (for order_position).
    """
    if object_type == "order":
        return [
            {"key": "code", "label": _("Order code"), "data_type": "text"},
            {"key": "status", "label": _("Order status"), "data_type": "text"},
            {"key": "total", "label": _("Order total"), "data_type": "number"},
            {"key": "datetime", "label": _("Order datetime"), "data_type": "date"},
            {"key": "email", "label": _("Order email"), "data_type": "text"},
            {"key": "invoice_name", "label": _("Invoice name"), "data_type": "text"},
            {
                "key": "invoice_company",
                "label": _("Invoice company"),
                "data_type": "text",
            },
            {
                "key": "invoice_address",
                "label": _("Invoice address"),
                "data_type": "text",
            },
        ]
    elif object_type == "order_position":
        if event is None:
            raise ValueError("event is required when object_type is 'order_position'")

        fields = [
            {"key": "attendee_name", "label": _("Attendee name"), "data_type": "text"},
            {
                "key": "attendee_email",
                "label": _("Attendee email"),
                "data_type": "text",
            },
        ]

        questions = event.questions.filter(active=True)
        for q in questions:
            if q.type == "F":
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
