import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet
from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.utils.timezone import make_aware
from datetime import datetime, time


@lru_cache(maxsize=1)
def _get_fernet() -> Fernet:
    key = base64.urlsafe_b64encode(
        hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    )
    return Fernet(key)


def encrypt(value: str) -> str:
    return _get_fernet().encrypt(value.encode()).decode()


def decrypt(value: str) -> str:
    return _get_fernet().decrypt(value.encode()).decode()


def get_hubspot_activity_logs(
    event, filter_type=None, date_from=None, date_to=None, search_query=None
):
    from .models import AuditLog, SyncLog

    activities = []

    AUDIT_ACTION_MAP = {
        "mapping_updated": (_("Field mapping settings were updated"), "settings"),
        "field_mapping_updated": (_("Field mapping settings were updated"), "settings"),
    }

    if filter_type in [None, "settings"]:
        audit_logs = AuditLog.objects.filter(event=event)

        if date_from:
            dt_from = make_aware(datetime.combine(date_from, time.min))
            audit_logs = audit_logs.filter(created_at__gte=dt_from)
        if date_to:
            dt_to = make_aware(datetime.combine(date_to, time.max))
            audit_logs = audit_logs.filter(created_at__lte=dt_to)

        for log in audit_logs:
            if log.action in [
                "connect",
                "disconnect",
                "token_refresh",
                "refresh_failed",
            ]:
                continue

            text, type_ = AUDIT_ACTION_MAP.get(log.action, (log.action, "settings"))

            if filter_type and filter_type != type_:
                continue

            if search_query and search_query.lower() not in str(text).lower():
                continue

            activities.append(
                {
                    "timestamp": log.created_at,
                    "text": text,
                    "type": type_,
                    "id": f"audit_{log.id}",
                    "user": "System",
                    "raw": log,
                }
            )

    if filter_type in [None, "sync"]:
        sync_logs = SyncLog.objects.filter(event=event).select_related(
            "object_mapping__content_type"
        )

        if date_from:
            dt_from = make_aware(datetime.combine(date_from, time.min))
            sync_logs = sync_logs.filter(created_at__gte=dt_from)
        if date_to:
            dt_to = make_aware(datetime.combine(date_to, time.max))
            sync_logs = sync_logs.filter(created_at__lte=dt_to)

        SYNC_STATUS_MESSAGES = {
            "success": _("%(obj_name)s synced to HubSpot successfully"),
            "failed": _("%(obj_name)s could not be synced to HubSpot"),
        }

        for log in sync_logs:
            # Skip actions that are already recorded in AuditLog (like connect, token refresh)
            if log.action in [
                "connect",
                "disconnect",
                "token_refresh",
                "refresh_failed",
            ]:
                continue

            obj_name = "Object"
            if log.object_mapping:
                if log.object_mapping.content_object:
                    obj = log.object_mapping.content_object
                    content_type_name = log.object_mapping.content_type.name.title()
                    model_name = log.object_mapping.content_type.model
                    if model_name == "orderposition" and hasattr(obj, "order"):
                        attendee_info = getattr(
                            obj, "attendee_name_cached", None
                        ) or getattr(obj, "attendee_email", None)
                        if not attendee_info and hasattr(obj.order, "email"):
                            attendee_info = obj.order.email
                        order_info = (
                            f" for Order {obj.order.code}"
                            if hasattr(obj.order, "code")
                            else ""
                        )
                        info_str = f" ({attendee_info})" if attendee_info else ""
                        obj_name = f"{content_type_name} {obj}{order_info}{info_str}"
                    elif model_name == "order" and hasattr(obj, "code"):
                        email_str = (
                            f" ({obj.email})"
                            if hasattr(obj, "email") and obj.email
                            else ""
                        )
                        obj_name = f"{content_type_name} {obj.code}{email_str}"
                    else:
                        obj_name = f"{content_type_name} {obj}"
                elif log.object_mapping.content_type:
                    obj_name = log.object_mapping.content_type.name.title()

            message_template = SYNC_STATUS_MESSAGES.get(
                log.status, _("%(obj_name)s sync is pending")
            )
            text = message_template % {"obj_name": obj_name}

            if search_query and search_query.lower() not in str(text).lower():
                continue

            activities.append(
                {
                    "timestamp": log.created_at,
                    "text": text,
                    "type": "sync",
                    "id": f"sync_{log.id}",
                    "user": "System",
                    "raw": log,
                }
            )

    activities.sort(key=lambda x: x["timestamp"], reverse=True)
    return activities
