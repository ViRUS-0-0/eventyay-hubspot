import datetime
import os

import requests
from django.core.cache import cache
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


class HubSpotFetchError(Exception):
    """Raised when fetching data from HubSpot API fails."""

    pass


def get_hubspot_properties(event, object_type: str) -> list[dict]:
    """
    Fetches and caches all properties for a given HubSpot object type (contact or deal).
    Returns a list of dictionaries with 'key', 'label', and 'data_type'.
    """
    cache_key = f"hubspot_properties_{event.id}_{object_type}"
    cached_props = cache.get(cache_key)
    if cached_props is not None:
        return cached_props

    token = get_valid_hubspot_token(event)
    if not token:
        raise HubSpotFetchError("Not connected to HubSpot or token is invalid.")

    url = f"https://api.hubapi.com/crm/v3/properties/{object_type}"
    headers = {"Authorization": f"Bearer {token}"}

    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
    except requests.RequestException as e:
        raise HubSpotFetchError(f"Failed to fetch properties from HubSpot: {str(e)}")

    data = response.json()
    results = data.get("results", [])

    properties = []
    for prop in results:
        # HubSpot's API returns internal/hidden properties by default.
        # We skip them to match the 210 visible properties in the HubSpot UI.
        if prop.get("hidden"):
            continue

        hubspot_type = prop.get("type", "string")

        # Map HubSpot types to eventyay field types ("text", "number", "date", "yes/no")
        if hubspot_type == "number":
            data_type = "number"
        elif hubspot_type in ("date", "datetime"):
            data_type = "date"
        elif hubspot_type == "bool":
            data_type = "yes/no"
        else:
            data_type = "text"

        properties.append(
            {
                "key": prop.get("name"),
                "label": prop.get("label"),
                "data_type": data_type,
            }
        )

    cache.set(cache_key, properties, timeout=3600)
    return properties


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
