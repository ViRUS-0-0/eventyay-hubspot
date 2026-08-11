from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.db.models import Max, Q
from django.utils.translation import gettext_lazy as _
from eventyay.base.models import Order, OrderPosition

from .models import (
    HubSpotFieldMapping,
    HubSpotObjectMapping,
    ObjectTypeMapping,
    SyncAction,
    SyncLog,
    SyncStatus,
)


def get_active_mappings_with_fields(event):
    """Yields (mapping, content_type) for mappings that have valid fields configured."""
    active_mappings = ObjectTypeMapping.objects.filter(event=event)
    order_ct = ContentType.objects.get_for_model(Order)
    position_ct = ContentType.objects.get_for_model(OrderPosition)

    for mapping in active_mappings:
        content_type = order_ct if mapping.eventyay_object_type == "order" else position_ct
        has_valid_fields = (
            HubSpotFieldMapping.objects.filter(
                event=event,
                content_type=content_type,
                hubspot_object_type=mapping.hubspot_object_type,
                is_active=True,
            )
            .exclude(eventyay_field="")
            .exclude(hubspot_property="")
            .exists()
        )
        if has_valid_fields:
            yield mapping, content_type


def get_unsynced_querysets(event):
    """
    Returns a list of tuples: (mapping, content_type, unsynced_queryset)
    """
    results = []
    for mapping, content_type in get_active_mappings_with_fields(event):
        synced_ids = set(
            HubSpotObjectMapping.objects.filter(
                event=event,
                content_type=content_type,
                hubspot_object_type=mapping.hubspot_object_type,
                last_synced_at__gte=mapping.updated_at,
            ).values_list("object_id", flat=True)
        )

        if mapping.eventyay_object_type == "order":
            qs = Order.objects.filter(event=event, status=Order.STATUS_PAID).exclude(id__in=synced_ids)
            results.append((mapping, content_type, qs))
        elif mapping.eventyay_object_type == "order_position":
            qs = (
                OrderPosition.objects.filter(order__event=event, order__status=Order.STATUS_PAID)
                .select_related("order")
                .exclude(id__in=synced_ids)
            )
            results.append((mapping, content_type, qs))

    return results


def get_unresolved_failed_logs(event):
    """
    Yields dicts containing 'object_mapping_id' and 'last_failure' for failed syncs
    that have not been successfully synced or dismissed since their last failure.
    """
    logs = (
        SyncLog.objects.filter(event=event, object_mapping__isnull=False)
        .values("object_mapping_id")
        .annotate(
            last_failure=Max("created_at", filter=Q(status=SyncStatus.FAILED)),
            last_success=Max("created_at", filter=Q(status=SyncStatus.SUCCESS)),
            last_dismiss=Max("created_at", filter=Q(action=SyncAction.DISMISS)),
        )
    )

    for entry in logs:
        if not entry["last_failure"]:
            continue

        res_dates = [d for d in (entry["last_success"], entry["last_dismiss"]) if d]
        last_resolution = max(res_dates) if res_dates else None

        if not last_resolution or entry["last_failure"] >= last_resolution:
            yield entry


def clear_sync_status_cache(event):
    """Clear the sync status counts cache for the given event."""
    cache_key = f"hubspot_sync_counts_{event.id}"
    cache.delete(cache_key)


def get_sync_status_counts(event):
    """Return (pending_count, failed_count) for the given event."""
    cache_key = f"hubspot_sync_counts_{event.id}"
    counts = cache.get(cache_key)
    if counts is not None:
        return counts

    pending_count = sum(qs.count() for _, _, qs in get_unsynced_querysets(event))
    failed_count = sum(1 for _ in get_unresolved_failed_logs(event))

    counts = (pending_count, failed_count)
    cache.set(cache_key, counts, 60)
    return counts


def get_failed_sync_records(event):
    """Return a list of dicts describing each failed sync record for the event.

    Each dict contains: object_mapping_id, order_code, hubspot_object_type,
    last_attempted_at, error_message, object_mapping (model instance).
    """
    records = []
    for entry in get_unresolved_failed_logs(event):
        # Get the actual failure log for details
        log = (
            SyncLog.objects.filter(
                event=event,
                object_mapping_id=entry["object_mapping_id"],
                status=SyncStatus.FAILED,
            )
            .select_related("object_mapping")
            .order_by("-created_at")
            .first()
        )
        if not log or not log.object_mapping:
            continue

        om = log.object_mapping
        # Resolve the source object to get a display code and accurate order_id
        try:
            source_obj = om.content_object
            if isinstance(source_obj, Order):
                code = source_obj.code
                obj_type = _("Order")
                actual_order_id = om.object_id
            elif isinstance(source_obj, OrderPosition):
                code = f"{source_obj.order.code}-{source_obj.positionid}"
                obj_type = _("Position")
                actual_order_id = source_obj.order_id
            else:
                code = str(om.object_id)
                obj_type = str(om.content_type)
                actual_order_id = om.object_id
        except Exception:
            code = str(om.object_id)
            obj_type = str(om.content_type)
            actual_order_id = om.object_id

        error = log.detail.get("error", "") if isinstance(log.detail, dict) else ""

        records.append(
            {
                "log_id": log.id,
                "object_mapping_id": om.id,
                "code": code,
                "obj_type": obj_type,
                "hubspot_type": om.hubspot_object_type,
                "last_attempted_at": log.created_at,
                "error_message": error,
                "error_readable": "",
                "order_id": actual_order_id,
                "content_type_id": om.content_type_id,
                "status": "failed",
            }
        )

    return records


def get_pending_sync_records(event):
    """Return a list of dicts for orders/positions missing a HubSpotObjectMapping."""
    records = []
    for mapping, content_type, qs in get_unsynced_querysets(event):
        if mapping.eventyay_object_type == "order":
            for obj in qs.values("id", "code"):
                records.append(
                    {
                        "log_id": None,
                        "object_mapping_id": None,
                        "code": obj["code"],
                        "obj_type": _("Order"),
                        "hubspot_type": mapping.hubspot_object_type,
                        "last_attempted_at": None,
                        "error_message": "",
                        "error_readable": "",
                        "order_id": obj["id"],
                        "content_type_id": content_type.id,
                        "status": "pending",
                    }
                )
        elif mapping.eventyay_object_type == "order_position":
            for obj in qs.values("id", "order_id", "order__code", "positionid"):
                records.append(
                    {
                        "log_id": None,
                        "object_mapping_id": None,
                        "code": f"{obj['order__code']}-{obj['positionid']}",
                        "obj_type": _("Position"),
                        "hubspot_type": mapping.hubspot_object_type,
                        "last_attempted_at": None,
                        "error_message": "",
                        "error_readable": "",
                        "order_id": obj["order_id"],
                        "content_type_id": content_type.id,
                        "status": "pending",
                    }
                )

    return records
