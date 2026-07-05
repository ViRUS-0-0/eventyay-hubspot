from django.db.models.signals import post_delete
from django.dispatch import receiver
from django.urls import resolve, reverse
from django.utils.translation import gettext_lazy as _
from django.contrib.contenttypes.models import ContentType
from eventyay.base.models import Order, OrderPosition
from eventyay.base.signals import periodic_task
from eventyay.control.signals import nav_event
from django_scopes import scope
from eventyay.base.signals import order_placed, order_paid, order_canceled
from .tasks import sync_order_to_hubspot
from .models import (
    HubSpotEventSettings,
    ObjectTypeMapping,
    HubSpotFieldMapping,
    HubSpotObjectMapping,
    HubSpotOAuthToken,
    AuditLog,
    SyncLog,
)
from django.utils.timezone import now
from datetime import timedelta


@receiver(nav_event, dispatch_uid="hubspot_nav")
def control_nav_import(sender, request=None, **kwargs):
    url = resolve(request.path_info)
    return [
        {
            "label": _("Hubspot"),
            "url": reverse(
                "plugins:hubspot:hubspot",
                kwargs={
                    "organizer": request.event.organizer.slug,
                    "event": request.event.slug,
                },
            ),
            "active": url.namespace == "plugins:hubspot" and url.url_name == "hubspot",
            "icon": "bar-chart",
        }
    ]


def _enqueue_hubspot_sync(sender, order, **kwargs):
    if not order:
        return
    with scope(organizer=order.event.organizer):
        settings = HubSpotEventSettings.objects.filter(event=order.event).first()
        if not settings or not settings.sync_enabled:
            return
        if not HubSpotOAuthToken.objects.filter(event=order.event).exists():
            return

    sync_order_to_hubspot.apply_async(args=[order.id, order.event.id], countdown=5)


@receiver(order_placed, dispatch_uid="hubspot_order_placed")
def on_order_placed(sender, order, **kwargs):
    _enqueue_hubspot_sync(sender, order, **kwargs)


@receiver(order_paid, dispatch_uid="hubspot_order_paid")
def on_order_paid(sender, order, **kwargs):
    _enqueue_hubspot_sync(sender, order, **kwargs)


@receiver(order_canceled, dispatch_uid="hubspot_order_canceled")
def on_order_canceled(sender, order, **kwargs):
    _enqueue_hubspot_sync(sender, order, **kwargs)


@receiver(
    post_delete,
    sender=ObjectTypeMapping,
    dispatch_uid="hubspot_object_type_mapping_delete",
)
def cleanup_associated_mappings(sender, instance, **kwargs):
    if instance.eventyay_object_type == "order":
        model_class = Order
    elif instance.eventyay_object_type == "order_position":
        model_class = OrderPosition
    else:
        return

    try:
        content_type = ContentType.objects.get_for_model(model_class)
    except ContentType.DoesNotExist:
        return

    # Delete associated Field Mappings
    HubSpotFieldMapping.objects.filter(
        event=instance.event,
        content_type=content_type,
        hubspot_object_type=instance.hubspot_object_type,
    ).delete()

    HubSpotObjectMapping.objects.filter(
        event=instance.event,
        content_type=content_type,
        hubspot_object_type=instance.hubspot_object_type,
    ).delete()


@receiver(periodic_task, dispatch_uid="hubspot_clear_audit_logs")
def clear_audit_logs(sender, **kwargs):
    days = 180

    threshold = now() - timedelta(days=days)
    AuditLog.objects.filter(created_at__lt=threshold).delete()
    SyncLog.objects.filter(created_at__lt=threshold).delete()
