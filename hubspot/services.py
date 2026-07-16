import datetime
import os
import uuid
import logging
import requests
from django.db import transaction
from django.utils.timezone import now
from django_scopes import scope

from .models import (
    AuditAction,
    AuditLog,
    HubSpotEventSettings,
    HubSpotOAuthToken,
    HubSpotProperty,
    HubSpotPropertySyncState,
    OrganizerHubSpotOAuthToken,
    OrganizerHubSpotSettings,
    SyncAction,
    SyncDirection,
    SyncLog,
    SyncStatus,
)


class HubSpotFetchError(Exception):
    """Raised when fetching data from HubSpot API fails."""

    pass


def get_hubspot_properties(
    event, object_type: str, force_sync: bool = False
) -> list[dict]:
    """
    Returns synced HubSpot properties from the DB.
    If no complete sync exists, is stale (older than TTL) or force_sync is True,
    triggers a chunk-wise sync first. Retries up to 4 times with 30 s / 60 s / 120 s delays.
    """
    sync_state = HubSpotPropertySyncState.objects.filter(
        event=event, object_type=object_type, is_complete=True
    ).first()

    try:
        ttl_minutes = int(os.environ.get("HUBSPOT_PROPERTY_SYNC_TTL_MINUTES", "10"))
    except ValueError:
        ttl_minutes = 10

    if (
        force_sync
        or not sync_state
        or (
            sync_state.completed_at
            and sync_state.completed_at
            < now() - datetime.timedelta(minutes=ttl_minutes)
        )
    ):
        try:
            sync_hubspot_properties(event, object_type)
        except HubSpotFetchError as e:
            logger = logging.getLogger(__name__)
            logger.error(f"Failed to fetch properties from HubSpot: {e}")
            if not HubSpotProperty.objects.filter(
                event=event, object_type=object_type
            ).exists():
                raise e

    return list(
        HubSpotProperty.objects.filter(event=event, object_type=object_type).values(
            "key", "label", "data_type"
        )
    )


def sync_hubspot_properties(event, object_type: str):
    """
    Fetches properties from HubSpot page by page, persisting each chunk to the DB.
    Resumes from the last cursor if a previous sync was interrupted.
    """
    token = get_valid_hubspot_token(event)
    if not token:
        raise HubSpotFetchError("Not connected to HubSpot or token is invalid.")

    sync_state, created = HubSpotPropertySyncState.objects.get_or_create(
        event=event,
        object_type=object_type,
        defaults={"sync_batch": uuid.uuid4()},
    )

    if sync_state.is_complete:
        sync_state.sync_batch = uuid.uuid4()
        sync_state.next_cursor = ""
        sync_state.is_complete = False
        sync_state.completed_at = None
        sync_state.save(
            update_fields=["sync_batch", "next_cursor", "is_complete", "completed_at"]
        )

    batch_id = sync_state.sync_batch
    cursor = sync_state.next_cursor
    base_url = f"https://api.hubapi.com/crm/v3/properties/{object_type}"
    headers = {"Authorization": f"Bearer {token}"}

    while True:
        params = {}
        if cursor:
            params["after"] = cursor

        try:
            response = requests.get(
                base_url, headers=headers, params=params, timeout=15
            )
            response.raise_for_status()
        except requests.RequestException:
            raise HubSpotFetchError(
                "Could not connect to HubSpot API. Please check your connection and try again."
            )

        data = response.json()
        results = data.get("results", [])

        for prop in results:
            if prop.get("hidden"):
                continue

            modification_metadata = prop.get("modificationMetadata", {})
            if modification_metadata.get("readOnlyValue"):
                continue

            if prop.get("calculated"):
                continue
            HubSpotProperty.objects.update_or_create(
                event=event,
                object_type=object_type,
                key=prop.get("name"),
                defaults={
                    "label": prop.get("label", ""),
                    "data_type": _map_hubspot_type(prop.get("type", "string")),
                    "sync_batch": batch_id,
                },
            )

        paging = data.get("paging", {})
        next_page = paging.get("next", {})
        cursor = next_page.get("after", "")

        if cursor:
            sync_state.next_cursor = cursor
            sync_state.save(update_fields=["next_cursor"])
        else:
            HubSpotProperty.objects.filter(
                event=event, object_type=object_type
            ).exclude(sync_batch=batch_id).delete()

            sync_state.is_complete = True
            sync_state.completed_at = now()
            sync_state.next_cursor = ""
            sync_state.save()
            break


_HUBSPOT_TYPE_MAP = {
    "number": "number",
    "date": "date",
    "datetime": "date",
    "bool": "yes/no",
}


def _map_hubspot_type(hubspot_type: str) -> str:
    return _HUBSPOT_TYPE_MAP.get(hubspot_type, "text")


def _refresh_token_record(token_obj, event_or_organizer, is_organizer=False):
    """
    Refreshes the token and updates the record.
    Returns the new access_token if successful, otherwise None.
    """
    logger = logging.getLogger(__name__)
    organizer = event_or_organizer if is_organizer else event_or_organizer.organizer

    try:
        response = requests.post(
            "https://api.hubapi.com/oauth/v1/token",
            data={
                "grant_type": "refresh_token",
                "client_id": os.environ.get("HUBSPOT_CLIENT_ID", ""),
                "client_secret": os.environ.get("HUBSPOT_CLIENT_SECRET", ""),
                "refresh_token": token_obj.refresh_token,
            },
            timeout=15,
        )
    except requests.RequestException as e:
        logger.error(
            "Network error refreshing HubSpot token for %s %s: %s",
            "organizer" if is_organizer else "event",
            event_or_organizer.slug,
            e,
        )
        AuditLog.objects.create(
            organizer=organizer,
            event=None if is_organizer else event_or_organizer,
            action=AuditAction.REFRESH_FAILED,
        )
        if not is_organizer:
            SyncLog.objects.create(
                event=event_or_organizer,
                action=SyncAction.REFRESH_FAILED,
                direction=SyncDirection.PUSH,
                status=SyncStatus.FAILED,
                detail={"error": str(e)},
            )
        return None

    if not response.ok:
        AuditLog.objects.create(
            organizer=organizer,
            event=None if is_organizer else event_or_organizer,
            action=AuditAction.REFRESH_FAILED,
        )
        if not is_organizer:
            SyncLog.objects.create(
                event=event_or_organizer,
                action=SyncAction.REFRESH_FAILED,
                direction=SyncDirection.PUSH,
                status=SyncStatus.FAILED,
                detail={"error": response.text},
            )
        return None

    data = response.json()
    expires_in = data.get("expires_in")
    expires_at = now() + datetime.timedelta(seconds=expires_in) if expires_in else None

    token_obj.access_token = data.get("access_token")
    if data.get("refresh_token"):
        token_obj.refresh_token = data.get("refresh_token")
    token_obj.expires_at = expires_at
    token_obj.save()

    AuditLog.objects.create(
        organizer=organizer,
        event=None if is_organizer else event_or_organizer,
        action=AuditAction.TOKEN_REFRESH,
    )
    if not is_organizer:
        SyncLog.objects.create(
            event=event_or_organizer,
            action=SyncAction.TOKEN_REFRESH,
            direction=SyncDirection.PUSH,
            status=SyncStatus.SUCCESS,
            detail={"message": "Token refreshed successfully"},
        )

    return token_obj.access_token


def get_valid_hubspot_token(event) -> str | None:
    """
    Returns a valid HubSpot access token for the given event.
    If the event has a token, uses it.
    Otherwise, checks the organizer's token if organizer sync is enabled.
    """
    with transaction.atomic(), scope(organizer=event.organizer):
        # 1. Try event token
        try:
            event_token = HubSpotOAuthToken.objects.select_for_update().get(event=event)
            if (
                event_token.expires_at
                and event_token.expires_at > now() + datetime.timedelta(minutes=5)
            ):
                return event_token.access_token
            return _refresh_token_record(event_token, event, is_organizer=False)
        except HubSpotOAuthToken.DoesNotExist:
            pass

        # 2. Check Organizer settings
        try:
            org_settings = OrganizerHubSpotSettings.objects.get(
                organizer=event.organizer
            )
            if not org_settings.sync_enabled:
                return None
        except OrganizerHubSpotSettings.DoesNotExist:
            return None

        # 3. Try Organizer token
        try:
            org_token = OrganizerHubSpotOAuthToken.objects.select_for_update().get(
                organizer=event.organizer
            )
            if (
                org_token.expires_at
                and org_token.expires_at > now() + datetime.timedelta(minutes=5)
            ):
                return org_token.access_token
            return _refresh_token_record(org_token, event.organizer, is_organizer=True)
        except OrganizerHubSpotOAuthToken.DoesNotExist:
            return None


def is_sync_enabled(event) -> bool:
    """
    Returns True if HubSpot sync is enabled for the event or its organizer.
    """
    try:
        if HubSpotEventSettings.objects.get(event=event).sync_enabled:
            return True
    except HubSpotEventSettings.DoesNotExist:
        pass

    try:
        return OrganizerHubSpotSettings.objects.get(
            organizer=event.organizer
        ).sync_enabled
    except OrganizerHubSpotSettings.DoesNotExist:
        return False


def is_auto_sync_enabled(event) -> bool:
    """
    Returns True if auto sync is enabled for the event.
    """
    try:
        return HubSpotEventSettings.objects.get(event=event).auto_sync_enabled
    except HubSpotEventSettings.DoesNotExist:
        return False
