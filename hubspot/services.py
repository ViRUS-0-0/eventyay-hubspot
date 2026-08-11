import datetime
import logging
import os

import requests
from django.core.cache import cache
from django.db import transaction
from django.utils.timezone import now
from django_scopes import scope

from .models import (
    AuditAction,
    AuditLog,
    HubSpotEventSettings,
    HubSpotOAuthToken,
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


def get_hubspot_properties(event, object_type: str, force_sync: bool = False) -> list[dict]:
    """
    Returns synced HubSpot properties from the cache.
    If no complete sync exists, fetches synchronously.
    If stale (older than TTL) or force_sync is True,
    triggers a background Celery task and serves stale data.
    """
    data_key = f"hubspot_properties_{event.id}_{object_type}"
    lock_key = f"hubspot_properties_lock_{event.id}_{object_type}"
    error_key = f"hubspot_properties_error_{event.id}_{object_type}"
    rate_limit_key = f"hubspot_auto_sync_limit_{event.id}_{object_type}"

    try:
        ttl_minutes = int(os.environ.get("HUBSPOT_PROPERTY_SYNC_TTL_MINUTES", "10"))
    except ValueError:
        ttl_minutes = 10

    if force_sync:
        cache.delete(error_key)

    has_error = cache.get(error_key) is not None
    cached_data = cache.get(data_key)

    is_stale = False
    if cached_data:
        fetched_at = cached_data.get("fetched_at")
        if not fetched_at or fetched_at < now() - datetime.timedelta(minutes=ttl_minutes):
            is_stale = True

    if not cached_data:
        if has_error and not force_sync:
            return []
        if cache.add(lock_key, "1", timeout=300):
            try:
                properties = sync_hubspot_properties(event, object_type)
                cache.set(
                    data_key,
                    {"fetched_at": now(), "properties": properties},
                    timeout=None,
                )
                cache.delete(error_key)
                return properties
            except Exception as e:
                cache.set(error_key, str(e), timeout=3600)
                raise
            finally:
                cache.delete(lock_key)
        else:
            cached_data = cache.get(data_key)
            if cached_data:
                return cached_data.get("properties", [])
            return []

    if force_sync or (not has_error and is_stale):
        if cache.add(lock_key, "1", timeout=300):
            if force_sync or cache.add(rate_limit_key, "1", timeout=30):
                from .tasks import refresh_hubspot_properties_task

                refresh_hubspot_properties_task.apply_async(args=[event.id, object_type])
            else:
                cache.delete(lock_key)

    return cached_data.get("properties", [])


def sync_hubspot_properties(event, object_type: str) -> list[dict]:
    """
    Fetches properties from HubSpot page by page and returns a list.
    """
    token = get_valid_hubspot_token(event)
    if not token:
        raise HubSpotFetchError("Not connected to HubSpot or token is invalid.")

    base_url = f"https://api.hubapi.com/crm/v3/properties/{object_type}"
    headers = {"Authorization": f"Bearer {token}"}
    cursor = ""
    properties = []
    lock_key = f"hubspot_properties_lock_{event.id}_{object_type}"

    while True:
        cache.set(lock_key, "1", timeout=300)
        params = {}
        if cursor:
            params["after"] = cursor

        try:
            response = requests.get(base_url, headers=headers, params=params, timeout=15)
            if response.status_code == 429:
                retry_after = response.headers.get("Retry-After")
                e = HubSpotFetchError("Rate limited by HubSpot")
                if retry_after:
                    e.retry_after = int(retry_after)
                raise e
            response.raise_for_status()
        except requests.RequestException as e:
            raise HubSpotFetchError(
                "Could not connect to HubSpot API. Please check your connection and try again."
            ) from e

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

            properties.append(
                {
                    "key": prop.get("name"),
                    "label": prop.get("label", ""),
                    "data_type": _map_hubspot_type(prop.get("type", "string")),
                }
            )

        paging = data.get("paging", {})
        next_page = paging.get("next", {})
        cursor = next_page.get("after", "")

        if not cursor:
            break

    return properties


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
    If sync is disabled for the event, returns None.
    If the event has a token, uses it.
    Otherwise, checks the organizer's token if organizer sync is enabled.
    """
    if not is_sync_enabled(event):
        return None

    with transaction.atomic(), scope(organizer=event.organizer):
        # 1. Try event token
        try:
            event_token = HubSpotOAuthToken.objects.select_for_update().get(event=event)
            if event_token.expires_at and event_token.expires_at > now() + datetime.timedelta(minutes=5):
                return event_token.access_token
            return _refresh_token_record(event_token, event, is_organizer=False)
        except HubSpotOAuthToken.DoesNotExist:
            pass

        # 2. Check Organizer settings
        try:
            org_settings = OrganizerHubSpotSettings.objects.get(organizer=event.organizer)
            if not org_settings.sync_enabled:
                return None
        except OrganizerHubSpotSettings.DoesNotExist:
            return None

        # 3. Try Organizer token
        try:
            org_token = OrganizerHubSpotOAuthToken.objects.select_for_update().get(organizer=event.organizer)
            if org_token.expires_at and org_token.expires_at > now() + datetime.timedelta(minutes=5):
                return org_token.access_token
            return _refresh_token_record(org_token, event.organizer, is_organizer=True)
        except OrganizerHubSpotOAuthToken.DoesNotExist:
            return None


def is_sync_enabled(event) -> bool:
    """
    Returns True if HubSpot sync is enabled and a valid token exists
    for the event or its organizer.
    If HubSpotEventSettings exists for the event, its sync_enabled overrides organizer fallback.
    """
    with scope(organizer=event.organizer):
        ev_settings = HubSpotEventSettings.objects.filter(event=event).first()
        if ev_settings is not None:
            if not ev_settings.sync_enabled:
                return False

        # Event sync is enabled (or settings don't exist yet), check if event has a token
        if HubSpotOAuthToken.objects.filter(event=event).exists():
            return True

        org_settings = OrganizerHubSpotSettings.objects.filter(organizer=event.organizer).first()
        if org_settings is not None and org_settings.sync_enabled:
            if OrganizerHubSpotOAuthToken.objects.filter(organizer=event.organizer).exists():
                return True

        return False


def is_auto_sync_enabled(event) -> bool:
    """
    Returns True if auto sync is enabled for the event.
    """
    try:
        return HubSpotEventSettings.objects.get(event=event).auto_sync_enabled
    except HubSpotEventSettings.DoesNotExist:
        return False
