import base64
import hashlib
from functools import lru_cache

from cryptography.fernet import Fernet
from django.conf import settings
from django.utils.translation import gettext_lazy as _


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


def get_hubspot_activity_logs(event, filter_type=None):
    from .models import AuditLog, SyncLog

    activities = []

    AUDIT_ACTION_MAP = {
        "mapping_updated": (_("Field mapping settings were updated"), "settings"),
        "field_mapping_updated": (_("Field mapping settings were updated"), "settings"),
    }

    if filter_type in [None, "settings"]:
        audit_logs = AuditLog.objects.filter(event=event)
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

            activities.append(
                {
                    "timestamp": log.created_at,
                    "text": text,
                    "type": type_,
                    "id": f"audit_{log.id}",
                    "user": log.user.get_full_name() if log.user else "System",
                    "raw": log,
                }
            )

    if filter_type in [None, "sync"]:
        sync_logs = SyncLog.objects.filter(event=event).select_related(
            "object_mapping__content_type"
        )

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

            obj_name = (
                log.object_mapping.content_type.name.title()
                if (log.object_mapping and log.object_mapping.content_type)
                else "Object"
            )

            message_template = SYNC_STATUS_MESSAGES.get(
                log.status, _("%(obj_name)s sync is pending")
            )
            text = message_template % {"obj_name": obj_name}

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
