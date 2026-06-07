from django.db import models
from django.db.models import JSONField
from django_scopes import ScopedManager
from .utils import decrypt, encrypt


class HubSpotOAuthToken(models.Model):
    event = models.OneToOneField("base.Event", on_delete=models.CASCADE)
    objects = models.Manager()
    scoped = ScopedManager(organizer="event__organizer")
    _access_token = models.TextField(db_column="access_token")
    _refresh_token = models.TextField(db_column="refresh_token")
    token_type = models.CharField(max_length=50, default="bearer")
    expires_at = models.DateTimeField(null=True, blank=True)
    hub_id = models.CharField(max_length=100, blank=True)
    scope = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    @property
    def access_token(self):
        return decrypt(self._access_token)

    @access_token.setter
    def access_token(self, value):
        self._access_token = encrypt(value)

    @property
    def refresh_token(self):
        return decrypt(self._refresh_token)

    @refresh_token.setter
    def refresh_token(self, value):
        self._refresh_token = encrypt(value)

    class Meta:
        verbose_name = "HubSpot OAuth Token"
        verbose_name_plural = "HubSpot OAuth Tokens"

    def __str__(self):
        return f"OAuth Token for {self.event.name}"


class HubSpotEventSettings(models.Model):
    event = models.OneToOneField("base.Event", on_delete=models.CASCADE)
    objects = models.Manager()
    scoped = ScopedManager(organizer="event__organizer")
    sync_enabled = models.BooleanField(default=False)
    sync_contacts = models.BooleanField(default=True)
    sync_deals = models.BooleanField(default=True)
    deal_pipeline = models.CharField(max_length=200, blank=True)
    deal_stage = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "HubSpot Event Settings"
        verbose_name_plural = "HubSpot Event Settings"

    def __str__(self):
        return f"HubSpot Settings for {self.event.name}"


class HubSpotObjectMapping(models.Model):
    event = models.ForeignKey("base.Event", on_delete=models.CASCADE)
    objects = models.Manager()
    scoped = ScopedManager(organizer="event__organizer")
    eventyay_model = models.CharField(max_length=50)
    eventyay_id = models.CharField(max_length=190)
    hubspot_object_type = models.CharField(max_length=50)
    hubspot_object_id = models.CharField(max_length=190)
    last_synced_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = (
            "event",
            "eventyay_model",
            "eventyay_id",
            "hubspot_object_type",
        )
        verbose_name = "HubSpot Object Mapping"
        verbose_name_plural = "HubSpot Object Mappings"

    def __str__(self):
        return f"{self.eventyay_model} ({self.eventyay_id}) -> {self.hubspot_object_type} ({self.hubspot_object_id})"


class HubSpotFieldMapping(models.Model):
    event = models.ForeignKey("base.Event", on_delete=models.CASCADE)
    objects = models.Manager()
    scoped = ScopedManager(organizer="event__organizer")
    eventyay_model = models.CharField(max_length=50)
    eventyay_field = models.CharField(max_length=190)
    hubspot_object_type = models.CharField(max_length=50)
    hubspot_property = models.CharField(max_length=190)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = (
            "event",
            "eventyay_model",
            "eventyay_field",
            "hubspot_object_type",
        )
        verbose_name = "HubSpot Field Mapping"
        verbose_name_plural = "HubSpot Field Mappings"

    def __str__(self):
        return f"{self.eventyay_model}.{self.eventyay_field} -> {self.hubspot_object_type}.{self.hubspot_property}"


class SyncLog(models.Model):
    class Action(models.TextChoices):
        CREATE = "create"
        UPDATE = "update"
        DELETE = "delete"
        CONNECT = "connect"
        DISCONNECT = "disconnect"
        TOKEN_REFRESH = "token_refresh"
        REFRESH_FAILED = "refresh_failed"

    class Direction(models.TextChoices):
        PUSH = "push"
        PULL = "pull"

    class Status(models.TextChoices):
        SUCCESS = "success"
        FAILED = "failed"
        PENDING = "pending"

    event = models.ForeignKey("base.Event", on_delete=models.CASCADE)
    objects = models.Manager()
    scoped = ScopedManager(organizer="event__organizer")
    object_mapping = models.ForeignKey(
        HubSpotObjectMapping, null=True, blank=True, on_delete=models.SET_NULL
    )
    action = models.CharField(max_length=20, choices=Action.choices)
    direction = models.CharField(max_length=10, choices=Direction.choices)
    status = models.CharField(max_length=10, choices=Status.choices)
    detail = JSONField(blank=True, default=dict)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        verbose_name = "Sync Log"
        verbose_name_plural = "Sync Logs"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.action} ({self.direction}) - {self.status} at {self.created_at}"
