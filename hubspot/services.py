import datetime
import os

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
