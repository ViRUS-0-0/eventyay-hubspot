from django.contrib import admin

from .models import (
    HubSpotEventSettings,
    HubSpotFieldMapping,
    HubSpotOAuthToken,
    HubSpotObjectMapping,
    SyncLog,
)


@admin.register(HubSpotOAuthToken)
class HubSpotOAuthTokenAdmin(admin.ModelAdmin):
    list_display = (
        "event",
        "hub_id",
        "expires_at",
        "created_at",
        "updated_at",
    )
    list_filter = ("event",)
    search_fields = ("event__name", "hub_id")
    readonly_fields = ("created_at", "updated_at")


@admin.register(HubSpotEventSettings)
class HubSpotEventSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "event",
        "sync_enabled",
        "sync_contacts",
        "sync_deals",
        "created_at",
        "updated_at",
    )
    list_filter = ("event", "sync_enabled", "sync_contacts", "sync_deals")
    search_fields = ("event__name", "deal_pipeline", "deal_stage")
    readonly_fields = ("created_at", "updated_at")


@admin.register(HubSpotObjectMapping)
class HubSpotObjectMappingAdmin(admin.ModelAdmin):
    list_display = (
        "event",
        "eventyay_model",
        "eventyay_id",
        "hubspot_object_type",
        "hubspot_object_id",
        "last_synced_at",
        "created_at",
    )
    list_filter = ("event", "eventyay_model", "hubspot_object_type")
    search_fields = ("event__name", "eventyay_id", "hubspot_object_id")
    readonly_fields = ("created_at",)


@admin.register(HubSpotFieldMapping)
class HubSpotFieldMappingAdmin(admin.ModelAdmin):
    list_display = (
        "event",
        "eventyay_model",
        "eventyay_field",
        "hubspot_object_type",
        "hubspot_property",
        "is_active",
        "created_at",
        "updated_at",
    )
    list_filter = ("event", "eventyay_model", "hubspot_object_type", "is_active")
    search_fields = ("event__name", "eventyay_field", "hubspot_property")
    readonly_fields = ("created_at", "updated_at")


@admin.register(SyncLog)
class SyncLogAdmin(admin.ModelAdmin):
    list_display = (
        "event",
        "action",
        "direction",
        "status",
        "created_at",
    )
    list_filter = ("event", "action", "direction", "status")
    search_fields = ("event__name",)
    readonly_fields = (
        "event",
        "object_mapping",
        "action",
        "direction",
        "status",
        "detail",
        "created_at",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
