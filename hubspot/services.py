import datetime
import os
import logging
import requests
from django.db import transaction
from django.utils.timezone import now
from django_scopes import scope

from .models import (
    AuditAction,
    AuditLog,
    HubSpotOAuthToken,
    SyncAction,
    SyncDirection,
    SyncLog,
    SyncStatus,
)
from django.core.cache import cache


class HubSpotFetchError(Exception):
    """Raised when fetching data from HubSpot API fails."""

    pass


def get_hubspot_properties(
    event, object_type: str, force_sync: bool = False
) -> list[dict]:
    """
    Returns synced HubSpot properties from the cache.
    If no complete sync exists, fetches synchronously.
    If stale (older than TTL) or force_sync is True,
    triggers a background Celery task and serves stale data.
    """
    data_key = f"hubspot_properties_{event.id}_{object_type}"
    lock_key = f"hubspot_properties_lock_{event.id}_{object_type}"

    try:
        ttl_minutes = int(os.environ.get("HUBSPOT_PROPERTY_SYNC_TTL_MINUTES", "10"))
    except ValueError:
        ttl_minutes = 10

    cached_data = cache.get(data_key)

    is_stale = False
    if cached_data:
        fetched_at = cached_data.get("fetched_at")
        if not fetched_at or fetched_at < now() - datetime.timedelta(
            minutes=ttl_minutes
        ):
            is_stale = True

    if not cached_data or force_sync or is_stale:
        if cache.add(lock_key, "1", timeout=60):
            from .tasks import refresh_hubspot_properties_task

            refresh_hubspot_properties_task.apply_async(args=[event.id, object_type])

    if not cached_data:
        return []

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

    while True:
        params = {}
        if cursor:
            params["after"] = cursor

        try:
            response = requests.get(
                base_url, headers=headers, params=params, timeout=15
            )
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


def get_valid_hubspot_token(event) -> str | None:
    """
    Returns a valid HubSpot access token for the given event.
    If the token expires within 5 minutes, it silently fetches a new one.
    Uses select_for_update() to prevent double-refresh on concurrent requests.
    """
    with transaction.atomic(), scope(organizer=event.organizer):
        try:
            token = HubSpotOAuthToken.objects.select_for_update().get(event=event)
        except HubSpotOAuthToken.DoesNotExist:
            return None

        # Check if the token is valid for at least 5 more minutes
        if token.expires_at and token.expires_at > now() + datetime.timedelta(
            minutes=5
        ):
            return token.access_token

        # Token is expired or expiring soon, refresh it
        logger = logging.getLogger(__name__)
        try:
            response = requests.post(
                "https://api.hubapi.com/oauth/v1/token",
                data={
                    "grant_type": "refresh_token",
                    "client_id": os.environ.get("HUBSPOT_CLIENT_ID", ""),
                    "client_secret": os.environ.get("HUBSPOT_CLIENT_SECRET", ""),
                    "refresh_token": token.refresh_token,
                },
                timeout=15,
            )
        except requests.RequestException as e:
            logger.error(
                "Network error refreshing HubSpot token for event %s: %s", event.slug, e
            )
            AuditLog.objects.create(
                organizer=event.organizer,
                event=event,
                action=AuditAction.REFRESH_FAILED,
            )
            SyncLog.objects.create(
                event=event,
                action=SyncAction.REFRESH_FAILED,
                direction=SyncDirection.PUSH,
                status=SyncStatus.FAILED,
                detail={"error": str(e)},
            )
            return None

        if not response.ok:
            # Refresh failed. Log and return None.
            SyncLog.objects.create(
                event=event,
                action=SyncAction.REFRESH_FAILED,
                direction=SyncDirection.PUSH,
                status=SyncStatus.FAILED,
                detail={"error": response.text},
            )
            AuditLog.objects.create(
                organizer=event.organizer,
                event=event,
                action=AuditAction.REFRESH_FAILED,
            )
            return None

        data = response.json()
        expires_in = data.get("expires_in")
        expires_at = (
            now() + datetime.timedelta(seconds=expires_in) if expires_in else None
        )

        # Update token locally
        token.access_token = data.get("access_token")
        if data.get("refresh_token"):
            token.refresh_token = data.get("refresh_token")
        token.expires_at = expires_at
        token.save()

        SyncLog.objects.create(
            event=event,
            action=SyncAction.TOKEN_REFRESH,
            direction=SyncDirection.PUSH,
            status=SyncStatus.SUCCESS,
            detail={"message": "Token refreshed successfully"},
        )
        AuditLog.objects.create(
            organizer=event.organizer,
            event=event,
            action=AuditAction.TOKEN_REFRESH,
        )

        return token.access_token
