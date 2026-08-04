import datetime
import logging
import os
import secrets
import urllib.parse

import requests
from django.contrib import messages
from django.shortcuts import redirect
from django.urls import reverse
from django.core.cache import cache
from django.core.exceptions import PermissionDenied
from django.utils.timezone import now
from django.utils.translation import gettext_lazy as _
from django.views.generic import ListView, TemplateView, View
from django_scopes import scope
from eventyay.base.models import Event, Order, OrderPosition, Organizer

from eventyay.control.permissions import (
    EventPermissionRequiredMixin,
    OrganizerPermissionRequiredMixin,
)
from eventyay.control.views import PaginationMixin
from eventyay.control.views.organizer_views.organizer_detail_view_mixin import (
    OrganizerDetailViewMixin,
)

from django.contrib.contenttypes.models import ContentType
from django.forms import modelformset_factory

from .forms import (
    HubSpotLogFilterForm,
    BaseHubSpotFieldMappingFormSet,
    HubSpotEventSettingsForm,
    HubSpotFieldMappingForm,
    ObjectTypeMappingFormSet,
)
from .models import (
    AuditAction,
    AuditLog,
    HubSpotEventSettings,
    HubSpotFieldMapping,
    HubSpotOAuthToken,
    ObjectTypeMapping,
    OrganizerHubSpotSettings,
    OrganizerHubSpotOAuthToken,
    SyncAction,
    SyncDirection,
    SyncLog,
    SyncStatus,
)
from .field_discovery import get_available_fields
from .services import get_hubspot_properties, get_valid_hubspot_token, is_sync_enabled
from .utils import get_hubspot_activity_logs
from .tasks import sync_all_mappings_task, sync_order_to_hubspot
from .sync_logic import (
    get_sync_status_counts,
    get_pending_sync_records,
    get_failed_sync_records,
    clear_sync_status_cache,
)


def get_client_ip(request):
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


class EventHubSpotSettingsView(EventPermissionRequiredMixin, TemplateView):
    """Landing page for HubSpot integration settings."""

    template_name = "hubspot/settings_landing.html"
    permission = "can_change_event_settings"

    def _get_formset(self, data=None):
        return ObjectTypeMappingFormSet(
            data,
            instance=self.request.event,
            queryset=ObjectTypeMapping.objects.filter(event=self.request.event),
        )

    def _get_settings_form(self, data=None):
        settings = HubSpotEventSettings.objects.filter(event=self.request.event).first()
        if not settings:
            if data is not None:
                settings, _ = HubSpotEventSettings.objects.get_or_create(
                    event=self.request.event
                )
            else:
                settings = HubSpotEventSettings(
                    event=self.request.event,
                    sync_enabled=is_sync_enabled(self.request.event),
                )
        return HubSpotEventSettingsForm(data, instance=settings)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        if not is_sync_enabled(self.request.event):
            context["is_connected"] = False
        else:
            try:
                token = self.request.event.hubspotoauthtoken
                context["is_connected"] = True
                context["connected_via"] = "event"
                context["hub_name"] = token.hub_name
                context["hub_id"] = token.hub_id
                context["connection_source"] = "event"
            except HubSpotOAuthToken.DoesNotExist:
                try:
                    org_token = self.request.event.organizer.organizerhubspotoauthtoken
                    context["is_connected"] = True
                    context["connected_via"] = "organizer"
                    context["hub_name"] = org_token.hub_name
                    context["hub_id"] = org_token.hub_id
                    context["connection_source"] = "organizer"
                except OrganizerHubSpotOAuthToken.DoesNotExist:
                    context["is_connected"] = False
                    context["connected_via"] = None

        if "formset" not in context:
            context["formset"] = self._get_formset()

        if "settings_form" not in context:
            context["settings_form"] = self._get_settings_form()

        context["recent_activities"] = get_hubspot_activity_logs(self.request.event)[:5]

        # Sync status counts for the notification banner
        if context["is_connected"]:
            pending_count, failed_count = get_sync_status_counts(self.request.event)
            context["pending_count"] = pending_count
            context["failed_count"] = failed_count

        return context

    def post(self, request, *args, **kwargs):
        form_type = request.POST.get("form_type", "mappings")

        if form_type == "mappings":
            formset = self._get_formset(request.POST)
            settings_form = self._get_settings_form()
            if formset.is_valid():
                formset.save()
                clear_sync_status_cache(request.event)
                AuditLog.objects.create(
                    organizer=request.event.organizer,
                    event=request.event,
                    action=AuditAction.MAPPING_UPDATED,
                    ip_address=get_client_ip(request),
                )
                messages.success(request, _("Object mappings saved."))
                return redirect(request.path)
        elif form_type == "settings":
            formset = self._get_formset()
            settings_form = self._get_settings_form(request.POST)
            if settings_form.is_valid():
                if "auto_sync_enabled" in settings_form.changed_data:
                    is_enabled = settings_form.cleaned_data["auto_sync_enabled"]
                    action = (
                        AuditAction.AUTO_SYNC_ENABLED
                        if is_enabled
                        else AuditAction.AUTO_SYNC_DISABLED
                    )
                    AuditLog.objects.create(
                        organizer=request.event.organizer,
                        event=request.event,
                        action=action,
                        ip_address=get_client_ip(request),
                    )
                settings_form.save()
                messages.success(request, _("Settings saved."))
                return redirect(request.path)
        else:
            return redirect(request.path)

        messages.error(
            request, _("We could not save your changes. See below for details.")
        )
        return self.render_to_response(
            self.get_context_data(formset=formset, settings_form=settings_form)
        )


class EventHubSpotConnectView(EventPermissionRequiredMixin, View):
    """Initiates HubSpot OAuth flow."""

    permission = "can_change_event_settings"

    def get(self, request, *args, **kwargs):
        state_token = secrets.token_urlsafe(16)
        request.session["hubspot_oauth_state"] = state_token
        # Pass the organizer and event slugs inside state parameter
        state = f"{state_token}:{request.event.organizer.slug}:{request.event.slug}"

        redirect_uri = os.environ.get("HUBSPOT_REDIRECT_URI", "")
        if not redirect_uri:
            redirect_uri = request.build_absolute_uri(
                reverse("plugins:hubspot:callback")
            )

        params = {
            "client_id": os.environ.get("HUBSPOT_CLIENT_ID", ""),
            "redirect_uri": redirect_uri,
            "scope": os.environ.get(
                "HUBSPOT_SCOPES",
                "oauth crm.objects.contacts.read crm.objects.contacts.write crm.objects.deals.read crm.objects.deals.write",
            ),
            "state": state,
        }
        url = "https://app.hubspot.com/oauth/authorize?" + urllib.parse.urlencode(
            params
        )
        return redirect(url)


class EventHubSpotCallbackView(View):
    """Handles callback from HubSpot OAuth."""

    def get(self, request, *args, **kwargs):
        error = request.GET.get("error")
        error_description = request.GET.get("error_description")
        state = request.GET.get("state", "")
        code = request.GET.get("code")

        # Unpack organizer and event slugs from the state parameter
        parts = state.split(":")
        state_token = parts[0] if len(parts) > 0 else ""
        organizer_slug = parts[1] if len(parts) > 1 else ""
        event_slug = parts[2] if len(parts) > 2 else ""

        is_organizer_flow = len(parts) == 2

        if (
            not state_token
            or not organizer_slug
            or (not is_organizer_flow and not event_slug)
        ):
            raise PermissionDenied(_("Invalid state parameter."))

        saved_state = request.session.pop("hubspot_oauth_state", None)

        if is_organizer_flow:
            settings_url = reverse(
                "plugins:hubspot:org_hubspot",
                kwargs={"organizer": organizer_slug},
            )
        else:
            settings_url = reverse(
                "plugins:hubspot:hubspot",
                kwargs={
                    "organizer": organizer_slug,
                    "event": event_slug,
                },
            )

        if error:
            messages.error(
                request,
                _("HubSpot authorization failed: {}").format(
                    error_description or error
                ),
            )
            return redirect(settings_url)

        if not state_token or state_token != saved_state:
            messages.error(request, _("Invalid state parameter. Please try again."))
            return redirect(settings_url)

        # Verify permissions manually
        if not request.user.is_authenticated:
            raise PermissionDenied()

        if is_organizer_flow:
            try:
                organizer = Organizer.objects.get(slug=organizer_slug)
            except Organizer.DoesNotExist:
                raise PermissionDenied(_("Organizer not found."))

            if not request.user.has_organizer_permission(
                organizer, "can_change_organizer_settings", request=request
            ):
                raise PermissionDenied(
                    _("You do not have permission to view this content.")
                )
        else:
            try:
                event = Event.objects.select_related("organizer").get(
                    slug=event_slug,
                    organizer__slug=organizer_slug,
                )
            except Event.DoesNotExist:
                raise PermissionDenied(_("Event not found."))

            if not request.user.has_event_permission(
                event.organizer, event, "can_change_event_settings", request=request
            ):
                raise PermissionDenied(
                    _("You do not have permission to view this content.")
                )

        redirect_uri = os.environ.get("HUBSPOT_REDIRECT_URI", "")
        if not redirect_uri:
            redirect_uri = request.build_absolute_uri(
                reverse("plugins:hubspot:callback")
            )

        response = requests.post(
            "https://api.hubapi.com/oauth/v1/token",
            data={
                "grant_type": "authorization_code",
                "client_id": os.environ.get("HUBSPOT_CLIENT_ID", ""),
                "client_secret": os.environ.get("HUBSPOT_CLIENT_SECRET", ""),
                "redirect_uri": redirect_uri,
                "code": code,
            },
            timeout=15,
        )

        if not response.ok:
            messages.error(request, _("Failed to exchange token with HubSpot."))
            return redirect(settings_url)

        data = response.json()
        expires_in = data.get("expires_in")
        expires_at = (
            now() + datetime.timedelta(seconds=expires_in) if expires_in else None
        )

        # Fetch portal info from HubSpot token info endpoint
        hub_id = ""
        hub_name = ""
        access_token = data.get("access_token", "")
        if access_token:
            try:
                info_resp = requests.get(
                    f"https://api.hubapi.com/oauth/v1/access-tokens/{access_token}",
                    timeout=10,
                )
                if info_resp.ok:
                    info = info_resp.json()
                    hub_id = str(info.get("hub_id", ""))
                    hub_name = info.get("hub_domain", "")
            except requests.RequestException:
                pass

        if is_organizer_flow:
            with scope(organizer=organizer):
                OrganizerHubSpotOAuthToken.objects.update_or_create(
                    organizer=organizer,
                    defaults={
                        "access_token": access_token,
                        "refresh_token": data.get("refresh_token"),
                        "token_type": data.get("token_type", "bearer"),
                        "expires_at": expires_at,
                        "hub_id": hub_id,
                        "hub_name": hub_name,
                        "scope": os.environ.get(
                            "HUBSPOT_SCOPES",
                            "oauth crm.objects.contacts.read crm.objects.contacts.write crm.objects.deals.read crm.objects.deals.write",
                        ),
                    },
                )

                OrganizerHubSpotSettings.objects.update_or_create(
                    organizer=organizer, defaults={"sync_enabled": True}
                )

                AuditLog.objects.create(
                    organizer=organizer,
                    event=None,
                    action=AuditAction.ORG_CONNECT,
                    ip_address=get_client_ip(request),
                )
        else:
            with scope(organizer=event.organizer):
                HubSpotOAuthToken.objects.update_or_create(
                    event=event,
                    defaults={
                        "access_token": access_token,
                        "refresh_token": data.get("refresh_token"),
                        "token_type": data.get("token_type", "bearer"),
                        "expires_at": expires_at,
                        "hub_id": hub_id,
                        "hub_name": hub_name,
                        "scope": os.environ.get(
                            "HUBSPOT_SCOPES",
                            "oauth crm.objects.contacts.read crm.objects.contacts.write crm.objects.deals.read crm.objects.deals.write",
                        ),
                    },
                )

                HubSpotEventSettings.objects.update_or_create(
                    event=event, defaults={"sync_enabled": True}
                )

                SyncLog.objects.create(
                    event=event,
                    action=SyncAction.CONNECT,
                    direction=SyncDirection.PUSH,
                    status=SyncStatus.SUCCESS,
                    detail={"message": "Connected to HubSpot"},
                )

                AuditLog.objects.create(
                    organizer=event.organizer,
                    event=event,
                    action=AuditAction.CONNECT,
                    ip_address=get_client_ip(request),
                )

        messages.success(request, _("Successfully connected to HubSpot."))
        return redirect(settings_url)


class EventHubSpotDisconnectView(EventPermissionRequiredMixin, View):
    """Disconnects from HubSpot, revoking the token and clearing local credentials."""

    permission = "can_change_event_settings"

    def post(self, request, *args, **kwargs):
        settings_url = reverse(
            "plugins:hubspot:hubspot",
            kwargs={
                "organizer": request.event.organizer.slug,
                "event": request.event.slug,
            },
        )

        try:
            token = HubSpotOAuthToken.objects.get(event=request.event)
            # Attempt to revoke at HubSpot
            try:
                # We use the refresh token to revoke, as per HubSpot docs.
                revoke_url = f"https://api.hubapi.com/oauth/v1/refresh-tokens/{token.refresh_token}"
                response = requests.delete(revoke_url, timeout=10)
                if not response.ok:
                    logger = logging.getLogger(__name__)
                    logger.warning(
                        f"Failed to revoke HubSpot token: {response.status_code} {response.text}"
                    )
            except requests.RequestException as e:
                logger = logging.getLogger(__name__)
                logger.warning(f"Error reaching HubSpot revoke endpoint: {e}")

            with scope(organizer=request.event.organizer):
                token.delete()
        except HubSpotOAuthToken.DoesNotExist:
            with scope(organizer=request.event.organizer):
                has_org_token = OrganizerHubSpotOAuthToken.objects.filter(
                    organizer=request.event.organizer
                ).exists()
                if not has_org_token or not is_sync_enabled(request.event):
                    messages.info(request, _("Not connected to HubSpot."))
                    return redirect(settings_url)

        # Always clear local credentials or disable sync
        with scope(organizer=request.event.organizer):
            HubSpotEventSettings.objects.update_or_create(
                event=request.event,
                defaults={"sync_enabled": False},
            )
            SyncLog.objects.create(
                event=request.event,
                action=SyncAction.DISCONNECT,
                direction=SyncDirection.PUSH,
                status=SyncStatus.SUCCESS,
                detail={"message": "Disconnected from HubSpot"},
            )
            AuditLog.objects.create(
                organizer=request.event.organizer,
                event=request.event,
                action=AuditAction.DISCONNECT,
                ip_address=get_client_ip(request),
            )

        # Clear synced HubSpot properties

        cache.delete(f"hubspot_properties_{request.event.id}_contacts")
        cache.delete(f"hubspot_properties_{request.event.id}_deals")
        cache.delete(f"hubspot_properties_error_{request.event.id}_contacts")
        cache.delete(f"hubspot_properties_error_{request.event.id}_deals")
        cache.delete(f"hubspot_properties_lock_{request.event.id}_contacts")
        cache.delete(f"hubspot_properties_lock_{request.event.id}_deals")
        cache.delete(f"hubspot_manual_sync_lock_{request.event.id}_contacts")
        cache.delete(f"hubspot_manual_sync_lock_{request.event.id}_deals")
        cache.delete(f"hubspot_auto_sync_limit_{request.event.id}_contacts")
        cache.delete(f"hubspot_auto_sync_limit_{request.event.id}_deals")

        messages.success(request, _("Successfully disconnected from HubSpot."))
        return redirect(settings_url)


class EventHubSpotLogView(EventPermissionRequiredMixin, PaginationMixin, ListView):
    """Full activity log page for HubSpot integration."""

    template_name = "hubspot/logs.html"
    permission = "can_change_event_settings"
    context_object_name = "activities"

    def get_queryset(self):
        form = HubSpotLogFilterForm(self.request.GET)
        filter_type = None
        date_from = None
        date_to = None
        search_query = None

        if form.is_valid():
            filter_type = form.cleaned_data.get("type")
            date_from = form.cleaned_data.get("date_from")
            date_to = form.cleaned_data.get("date_until")
            search_query = form.cleaned_data.get("query")

        if filter_type not in ["sync", "settings"]:
            filter_type = None

        return get_hubspot_activity_logs(
            self.request.event,
            filter_type=filter_type,
            date_from=date_from,
            date_to=date_to,
            search_query=search_query,
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filter_form"] = HubSpotLogFilterForm(self.request.GET)
        return context

    def post(self, request, *args, **kwargs):
        if request.POST.get("action") == "delete":
            if request.POST.get("select_all_pages") == "1":
                qs = self.get_queryset()
                if qs.search_query:
                    # If there's a search query, we must iterate since filtering happens in Python
                    audit_ids = []
                    sync_ids = []
                    for item in qs:
                        if item["id"].startswith("audit_"):
                            audit_ids.append(int(item["id"].split("_")[1]))
                        elif item["id"].startswith("sync_"):
                            sync_ids.append(int(item["id"].split("_")[1]))
                    if audit_ids:
                        AuditLog.objects.filter(
                            event=request.event, id__in=audit_ids
                        ).delete()
                    if sync_ids:
                        SyncLog.objects.filter(
                            event=request.event, id__in=sync_ids
                        ).delete()
                else:
                    # If no search query, we can directly delete the querysets
                    qs.audit_logs.delete()
                    qs.sync_logs.delete()
            else:
                log_ids = request.POST.getlist("log_id")
                audit_ids = []
                sync_ids = []
                for log_id in log_ids:
                    if log_id.startswith("audit_"):
                        try:
                            audit_ids.append(int(log_id.split("_")[1]))
                        except (ValueError, IndexError):
                            pass
                    elif log_id.startswith("sync_"):
                        try:
                            sync_ids.append(int(log_id.split("_")[1]))
                        except (ValueError, IndexError):
                            pass

                if audit_ids:
                    AuditLog.objects.filter(
                        event=request.event, id__in=audit_ids
                    ).delete()
                if sync_ids:
                    SyncLog.objects.filter(
                        event=request.event, id__in=sync_ids
                    ).delete()

            messages.success(request, _("Selected logs have been deleted."))
            return redirect(
                request.path_info + "?" + request.META.get("QUERY_STRING", "")
            )

        return self.get(request, *args, **kwargs)


class EventHubSpotFieldMappingView(EventPermissionRequiredMixin, TemplateView):
    """View to manage field mapping rows for a specific object mapping type."""

    template_name = "hubspot/field_mapping.html"
    permission = "can_change_event_settings"

    def _get_formset_kwargs(self, mapping_id, request):
        try:
            mapping = ObjectTypeMapping.objects.get(pk=mapping_id, event=request.event)
        except ObjectTypeMapping.DoesNotExist:
            raise PermissionDenied(_("Invalid object mapping."))

        if mapping.eventyay_object_type == "order":
            content_type = ContentType.objects.get_for_model(Order)
        elif mapping.eventyay_object_type == "order_position":
            content_type = ContentType.objects.get_for_model(OrderPosition)
        else:
            raise PermissionDenied(_("Unsupported eventyay object type."))

        hubspot_object_type = mapping.hubspot_object_type

        queryset = HubSpotFieldMapping.objects.filter(
            event=request.event,
            content_type=content_type,
            hubspot_object_type=hubspot_object_type,
        )

        FormSet = modelformset_factory(
            HubSpotFieldMapping,
            form=HubSpotFieldMappingForm,
            formset=BaseHubSpotFieldMappingFormSet,
            extra=1 if not queryset.exists() else 0,
            can_delete=True,
        )

        eventyay_fields = get_available_fields(
            mapping.eventyay_object_type, event=request.event
        )
        sync_error = None
        try:
            hubspot_properties = get_hubspot_properties(
                request.event, mapping.hubspot_object_type
            )
        except Exception as e:
            logger = logging.getLogger(__name__)
            logger.error(
                "Failed to load HubSpot properties for event %s: %s",
                request.event.slug,
                e,
            )
            sync_error = _(
                "Could not retrieve HubSpot properties. "
                "Please check your connection and try again."
            )
            hubspot_properties = []

        error_key = (
            f"hubspot_properties_error_{request.event.id}_{mapping.hubspot_object_type}"
        )
        if cache.get(error_key):
            sync_error = _(
                "HubSpot properties sync failed repeatedly. "
                "HubSpot may be unreachable or you might need to reconnect."
            )

        is_fetching_properties = (
            cache.get(
                f"hubspot_manual_sync_lock_{request.event.id}_{mapping.hubspot_object_type}"
            )
            is not None
        )

        form_kwargs = {
            "eventyay_fields": eventyay_fields,
            "hubspot_properties": hubspot_properties,
            "is_fetching_properties": is_fetching_properties,
        }

        return {
            "FormSet": FormSet,
            "queryset": queryset,
            "form_kwargs": form_kwargs,
            "content_type": content_type,
            "hubspot_object_type": hubspot_object_type,
            "mapping": mapping,
            "sync_error": sync_error,
            "is_fetching_properties": is_fetching_properties,
        }

    def get(self, request, *args, **kwargs):
        if request.GET.get("force_sync") == "1":
            mapping_id = self.kwargs.get("mapping_id")
            try:
                mapping = ObjectTypeMapping.objects.get(
                    pk=mapping_id, event=request.event
                )
            except ObjectTypeMapping.DoesNotExist:
                raise PermissionDenied(_("Invalid object mapping."))

            rate_limit_key = f"hubspot_manual_sync_limit_{request.event.id}_{mapping.hubspot_object_type}"

            if cache.add(rate_limit_key, "1", timeout=30):
                error_key = f"hubspot_properties_error_{request.event.id}_{mapping.hubspot_object_type}"
                cache.delete(error_key)
                lock_key = f"hubspot_manual_sync_lock_{request.event.id}_{mapping.hubspot_object_type}"
                cache.add(lock_key, "1", timeout=60)

                from .tasks import refresh_hubspot_properties_task

                refresh_hubspot_properties_task.apply_async(
                    args=[request.event.id, mapping.hubspot_object_type]
                )
                messages.success(request, _("Sync task started in the background."))
            else:
                messages.error(request, _("Please wait a moment before trying again."))

            clean_url = reverse(
                "plugins:hubspot:mapping_fields",
                kwargs={
                    "organizer": request.event.organizer.slug,
                    "event": request.event.slug,
                    "mapping_id": mapping_id,
                },
            )
            return redirect(clean_url)

        return super().get(request, *args, **kwargs)

    def get_context_data(self, setup=None, **kwargs):
        context = super().get_context_data(**kwargs)
        mapping_id = self.kwargs.get("mapping_id")

        if setup is None:
            setup = self._get_formset_kwargs(mapping_id, self.request)

        context["content_type"] = setup["content_type"]
        context["hubspot_object_type"] = setup["hubspot_object_type"]
        context["mapping"] = setup["mapping"]
        context["sync_error"] = setup.get("sync_error")
        context["is_fetching_properties"] = setup.get("is_fetching_properties", False)

        if "formset" not in context:
            context["formset"] = setup["FormSet"](
                queryset=setup["queryset"], form_kwargs=setup["form_kwargs"]
            )

        context["has_rows"] = setup["queryset"].exists()

        return context

    def post(self, request, *args, **kwargs):
        mapping_id = self.kwargs.get("mapping_id")
        setup = self._get_formset_kwargs(mapping_id, request)

        formset = setup["FormSet"](
            request.POST, queryset=setup["queryset"], form_kwargs=setup["form_kwargs"]
        )

        if formset.is_valid():
            instances = formset.save(commit=False)

            for instance in instances:
                instance.event = request.event
                instance.content_type = setup["content_type"]
                instance.hubspot_object_type = setup["hubspot_object_type"]
                instance.save()

            for obj in formset.deleted_objects:
                obj.delete()

            if formset.has_changed():
                setup["mapping"].save()
                clear_sync_status_cache(request.event)

            AuditLog.objects.create(
                organizer=request.event.organizer,
                event=request.event,
                action=AuditAction.FIELD_MAPPING_UPDATED,
                ip_address=get_client_ip(request),
            )

            messages.success(
                request, _("Field mapping configuration saved successfully.")
            )
            return redirect(
                reverse(
                    "plugins:hubspot:mapping_fields",
                    kwargs={
                        "organizer": request.event.organizer.slug,
                        "event": request.event.slug,
                        "mapping_id": mapping_id,
                    },
                )
            )
        else:
            messages.error(
                request,
                _(
                    "There were errors saving your configuration. Please check the form."
                ),
            )
            return self.render_to_response(
                self.get_context_data(setup=setup, formset=formset)
            )


class EventHubSpotSyncMappingView(EventPermissionRequiredMixin, View):
    """Triggers background sync for all mappings of the event."""

    permission = "can_change_event_settings"

    def post(self, request, *args, **kwargs):
        settings_url = reverse(
            "plugins:hubspot:hubspot",
            kwargs={
                "organizer": request.event.organizer.slug,
                "event": request.event.slug,
            },
        )

        token = get_valid_hubspot_token(request.event)
        if not token:
            messages.error(
                request,
                _("Not connected to HubSpot or sync is disabled for this event."),
            )
            return redirect(settings_url)

        sync_all_mappings_task.apply_async(args=[request.event.id])

        messages.success(
            request,
            _(
                "Mapping sync started in the background. Depending on the amount of data, this may take a few minutes."
            ),
        )
        return redirect(settings_url)


class SyncProblemsView(EventPermissionRequiredMixin, PaginationMixin, ListView):
    """Lists all orders/positions that are either unsynced or have failed syncs."""

    template_name = "hubspot/sync_problems.html"
    permission = "can_change_event_settings"
    context_object_name = "records"
    paginate_by = 25

    def get_queryset(self):
        from .forms import SyncProblemsFilterForm
        from datetime import datetime, time
        from django.utils.timezone import make_aware

        self.filter_form = SyncProblemsFilterForm(
            data=self.request.GET, prefix="filter"
        )

        status_filter = ""
        query = ""
        date_from = None
        date_to = None

        if self.filter_form.is_valid():
            status_filter = self.filter_form.cleaned_data.get("status", "")
            query = self.filter_form.cleaned_data.get("query", "").lower()
            date_from = self.filter_form.cleaned_data.get("date_from")
            date_to = self.filter_form.cleaned_data.get("date_to")

        records = []
        if status_filter != "failed":
            records.extend(get_pending_sync_records(self.request.event))
        if status_filter != "pending":
            records.extend(get_failed_sync_records(self.request.event))

        # Filter by query
        if query:
            records = [
                r
                for r in records
                if query in r["code"].lower()
                or (r["error_message"] and query in r["error_message"].lower())
            ]

        # Filter by dates (only applies to records with last_attempted_at, i.e., failed records)
        if date_from:
            dt_from = make_aware(datetime.combine(date_from, time.min))
            records = [
                r
                for r in records
                if r["last_attempted_at"] and r["last_attempted_at"] >= dt_from
            ]
        if date_to:
            dt_to = make_aware(datetime.combine(date_to, time.max))
            records = [
                r
                for r in records
                if r["last_attempted_at"] and r["last_attempted_at"] <= dt_to
            ]

        # Make error messages more human-readable
        for r in records:
            if r["error_message"]:
                err = str(r["error_message"])
                # Map common HubSpot errors
                if "409 Client Error" in err or "already exists" in err:
                    r["error_readable"] = _(
                        "This record already exists in HubSpot and could not be updated."
                    )
                elif (
                    "400 Client Error" in err or "Property values were not valid" in err
                ):
                    r["error_readable"] = _(
                        "One or more mapped fields contain invalid data for HubSpot."
                    )
                elif (
                    "401 Client Error" in err
                    or "Authentication credentials not found" in err
                ):
                    r["error_readable"] = _(
                        "HubSpot authentication failed. Please reconnect."
                    )
                else:
                    r["error_readable"] = _("An unexpected error occurred during sync.")
            else:
                r["error_readable"] = ""

        # Sort: failed first, then pending; within each group by code
        status_order = {"failed": 0, "pending": 1}
        records.sort(key=lambda r: (status_order.get(r["status"], 2), r["code"]))
        return records

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filter_form"] = getattr(self, "filter_form", None)
        context["has_failed"] = any(
            r["status"] == "failed" for r in get_failed_sync_records(self.request.event)
        )
        return context


class RetrySyncView(EventPermissionRequiredMixin, View):
    """Re-queues a single order for sync."""

    permission = "can_change_event_settings"

    def post(self, request, *args, **kwargs):
        order_id = kwargs["order_id"]
        sync_order_to_hubspot.apply_async(args=[order_id, request.event.id])
        messages.success(request, _("Sync retry queued."))
        return redirect(
            reverse(
                "plugins:hubspot:sync_problems",
                kwargs={
                    "organizer": request.event.organizer.slug,
                    "event": request.event.slug,
                },
            )
        )


class RetryAllFailedView(EventPermissionRequiredMixin, View):
    """Re-queues all failed orders for sync."""

    permission = "can_change_event_settings"

    def post(self, request, *args, **kwargs):
        failed_records = get_failed_sync_records(request.event)
        order_ids = {r["order_id"] for r in failed_records}
        for order_id in order_ids:
            sync_order_to_hubspot.apply_async(args=[order_id, request.event.id])
        messages.success(
            request,
            _("Retry queued for %(count)d orders.") % {"count": len(order_ids)},
        )
        return redirect(
            reverse(
                "plugins:hubspot:sync_problems",
                kwargs={
                    "organizer": request.event.organizer.slug,
                    "event": request.event.slug,
                },
            )
        )


class SyncRetryBulkView(EventPermissionRequiredMixin, View):
    """Re-queues selected orders for sync."""

    permission = "can_change_event_settings"

    def post(self, request, *args, **kwargs):
        order_ids = request.POST.getlist("records")
        if order_ids:
            # Validate IDs belong to this event
            valid_order_ids = set(
                Order.objects.filter(event=request.event, id__in=order_ids).values_list(
                    "id", flat=True
                )
            )
            valid_order_ids_str = {str(i) for i in valid_order_ids}
            validated_order_ids = [o for o in order_ids if o in valid_order_ids_str]

            if validated_order_ids:
                for order_id in validated_order_ids:
                    sync_order_to_hubspot.apply_async(
                        args=[int(order_id), request.event.id]
                    )
                messages.success(
                    request,
                    _("Retry queued for %(count)d orders.")
                    % {"count": len(validated_order_ids)},
                )
            else:
                messages.warning(request, _("No valid records selected."))
        else:
            messages.warning(request, _("No records selected."))

        return redirect(
            reverse(
                "plugins:hubspot:sync_problems",
                kwargs={
                    "organizer": request.event.organizer.slug,
                    "event": request.event.slug,
                },
            )
        )


class DismissSyncView(EventPermissionRequiredMixin, View):
    """Dismisses a failed sync record by creating a DISMISS SyncLog entry."""

    permission = "can_change_event_settings"

    def post(self, request, *args, **kwargs):
        log_id = kwargs["log_id"]
        try:
            failed_log = SyncLog.objects.get(
                id=log_id,
                event=request.event,
                status=SyncStatus.FAILED,
            )
        except SyncLog.DoesNotExist:
            messages.error(request, _("Sync record not found."))
            return redirect(
                reverse(
                    "plugins:hubspot:sync_problems",
                    kwargs={
                        "organizer": request.event.organizer.slug,
                        "event": request.event.slug,
                    },
                )
            )

        SyncLog.objects.create(
            event=request.event,
            object_mapping=failed_log.object_mapping,
            action=SyncAction.DISMISS,
            direction=failed_log.direction,
            status=SyncStatus.SUCCESS,
            detail={"message": "Dismissed by organizer"},
        )
        messages.success(request, _("Sync record dismissed."))
        return redirect(
            reverse(
                "plugins:hubspot:sync_problems",
                kwargs={
                    "organizer": request.event.organizer.slug,
                    "event": request.event.slug,
                },
            )
        )


class SyncOrderNowView(EventPermissionRequiredMixin, View):
    """Re-queues a single order for sync directly from the order detail page."""

    permission = "can_change_event_settings"

    def post(self, request, *args, **kwargs):
        order_code = kwargs["order"]
        try:
            order = Order.objects.get(code=order_code, event=request.event)

            if order.status != Order.STATUS_PAID:
                messages.error(request, _("Only paid orders can be synced."))
                return redirect(
                    reverse(
                        "control:event.order",
                        kwargs={
                            "organizer": request.event.organizer.slug,
                            "event": request.event.slug,
                            "code": order_code,
                        },
                    )
                )

            # Create a pending SyncLog so the UI updates immediately
            from .models import HubSpotObjectMapping

            content_type = ContentType.objects.get_for_model(Order)
            mapping = HubSpotObjectMapping.objects.filter(
                event=request.event, content_type=content_type, object_id=order.id
            ).first()

            SyncLog.objects.create(
                event=request.event,
                object_mapping=mapping,
                action=SyncAction.UPDATE,
                direction=SyncDirection.PUSH,
                status=SyncStatus.PENDING,
                detail={
                    "message": f"Manual sync requested for order {order.code}",
                    "order_code": order.code,
                },
            )

            sync_order_to_hubspot.apply_async(args=[order.id, request.event.id])
            messages.success(request, _("Sync task queued."))
        except Order.DoesNotExist:
            messages.error(request, _("Order not found."))

        return redirect(
            reverse(
                "control:event.order",
                kwargs={
                    "organizer": request.event.organizer.slug,
                    "event": request.event.slug,
                    "code": order_code,
                },
            )
        )


class OrganizerHubSpotSettingsView(
    OrganizerPermissionRequiredMixin, OrganizerDetailViewMixin, TemplateView
):
    """Organizer-level settings page for HubSpot."""

    template_name = "hubspot/organizer_settings.html"
    permission = "can_change_organizer_settings"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            token = self.request.organizer.organizerhubspotoauthtoken
            context["is_connected"] = True
            context["hub_name"] = token.hub_name
            context["hub_id"] = token.hub_id
            context["connected_since"] = token.created_at
        except OrganizerHubSpotOAuthToken.DoesNotExist:
            context["is_connected"] = False

        settings, _created = OrganizerHubSpotSettings.objects.get_or_create(
            organizer=self.request.organizer
        )
        context["sync_enabled"] = settings.sync_enabled

        events = list(
            self.request.organizer.events.all().order_by("-date_from", "name")
        )
        if not events:
            context["events"] = []
            return context

        settings_map = dict(
            HubSpotEventSettings.objects.filter(event__in=events).values_list(
                "event", "sync_enabled"
            )
        )
        tokens_set = set(
            HubSpotOAuthToken.objects.filter(event__in=events).values_list(
                "event", flat=True
            )
        )
        obj_mappings_set = set(
            ObjectTypeMapping.objects.filter(event__in=events).values_list(
                "event", flat=True
            )
        )
        field_mappings_set = set(
            HubSpotFieldMapping.objects.filter(event__in=events).values_list(
                "event", flat=True
            )
        )

        for event in events:
            # Toggle state
            event.event_sync_enabled = settings_map.get(event.id, settings.sync_enabled)

            # Connection status
            has_event_token = event.id in tokens_set
            if has_event_token and event.event_sync_enabled:
                event.connection_status_text = _("Connected (Event token)")
                event.connection_badge_class = "success"
            elif context["is_connected"] and event.event_sync_enabled:
                event.connection_status_text = _("Connected (Organizer fallback)")
                event.connection_badge_class = "info"
            else:
                event.connection_status_text = _("Not connected")
                event.connection_badge_class = "muted"

            # Mapping status
            has_mappings = (
                event.id in obj_mappings_set or event.id in field_mappings_set
            )
            if has_mappings:
                event.mapping_status_text = _("Custom")
                event.mapping_badge_class = "primary"
            else:
                event.mapping_status_text = _("Organizer default")
                event.mapping_badge_class = "default"

        context["events"] = events
        return context

    def post(self, request, *args, **kwargs):
        form_type = request.POST.get("form_type")
        if form_type == "toggle":
            settings, created = OrganizerHubSpotSettings.objects.get_or_create(
                organizer=request.organizer
            )
            settings.sync_enabled = request.POST.get("sync_enabled") == "on"
            settings.save()

            AuditLog.objects.create(
                organizer=request.organizer,
                event=None,
                action=AuditAction.ORG_TOGGLE,
                ip_address=get_client_ip(request),
            )
            messages.success(request, _("Settings saved."))

        elif form_type == "events_toggle":
            event_ids = request.POST.getlist("event_ids")
            events = list(request.organizer.events.filter(id__in=event_ids))
            existing_settings = {
                s.event_id: s
                for s in HubSpotEventSettings.objects.filter(event__in=events)
            }
            to_create = []
            to_update = []
            events_to_clear_token = []
            for event in events:
                is_checked = f"event_sync_enabled_{event.id}" in request.POST
                ev_settings = existing_settings.get(event.id)
                if ev_settings:
                    if ev_settings.sync_enabled != is_checked:
                        ev_settings.sync_enabled = is_checked
                        to_update.append(ev_settings)
                        if not is_checked:
                            events_to_clear_token.append(event)
                else:
                    if not is_checked:
                        events_to_clear_token.append(event)
                    to_create.append(
                        HubSpotEventSettings(event=event, sync_enabled=is_checked)
                    )

            if to_create:
                HubSpotEventSettings.objects.bulk_create(to_create)
            if to_update:
                HubSpotEventSettings.objects.bulk_update(to_update, ["sync_enabled"])

            if to_create or to_update:
                AuditLog.objects.create(
                    organizer=request.organizer,
                    event=None,
                    action=AuditAction.ORG_TOGGLE,
                    ip_address=get_client_ip(request),
                )

            if events_to_clear_token:
                tokens_to_delete = HubSpotOAuthToken.objects.filter(
                    event__in=events_to_clear_token
                )
                for token in tokens_to_delete:
                    try:
                        revoke_url = f"https://api.hubapi.com/oauth/v1/refresh-tokens/{token.refresh_token}"
                        requests.delete(revoke_url, timeout=10)
                    except Exception:
                        pass
                tokens_to_delete.delete()

            messages.success(request, _("Event sync settings saved."))

        return redirect(
            reverse(
                "plugins:hubspot:org_hubspot",
                kwargs={"organizer": request.organizer.slug},
            )
        )


class OrganizerHubSpotConnectView(OrganizerPermissionRequiredMixin, View):
    """Initiates organizer-level HubSpot OAuth flow."""

    permission = "can_change_organizer_settings"

    def get(self, request, *args, **kwargs):
        state_token = secrets.token_urlsafe(16)
        request.session["hubspot_oauth_state"] = state_token
        # Pass only the organizer slug inside state parameter (2 segments total)
        state = f"{state_token}:{request.organizer.slug}"

        redirect_uri = os.environ.get("HUBSPOT_REDIRECT_URI", "")
        if not redirect_uri:
            redirect_uri = request.build_absolute_uri(
                reverse("plugins:hubspot:callback")
            )

        params = {
            "client_id": os.environ.get("HUBSPOT_CLIENT_ID", ""),
            "redirect_uri": redirect_uri,
            "scope": os.environ.get(
                "HUBSPOT_SCOPES",
                "oauth crm.objects.contacts.read crm.objects.contacts.write crm.objects.deals.read crm.objects.deals.write",
            ),
            "state": state,
        }
        url = "https://app.hubspot.com/oauth/authorize?" + urllib.parse.urlencode(
            params
        )
        return redirect(url)


class OrganizerHubSpotDisconnectView(OrganizerPermissionRequiredMixin, View):
    """Disconnects from HubSpot at the organizer level."""

    permission = "can_change_organizer_settings"

    def post(self, request, *args, **kwargs):
        settings_url = reverse(
            "plugins:hubspot:org_hubspot",
            kwargs={"organizer": request.organizer.slug},
        )

        try:
            token = OrganizerHubSpotOAuthToken.objects.get(organizer=request.organizer)
        except OrganizerHubSpotOAuthToken.DoesNotExist:
            messages.info(request, _("Not connected to HubSpot."))
            return redirect(settings_url)

        # Attempt to revoke at HubSpot
        try:
            revoke_url = (
                f"https://api.hubapi.com/oauth/v1/refresh-tokens/{token.refresh_token}"
            )
            response = requests.delete(revoke_url, timeout=10)
            if not response.ok:
                logger = logging.getLogger(__name__)
                logger.warning(
                    f"Failed to revoke HubSpot organizer token: {response.status_code} {response.text}"
                )
        except requests.RequestException as e:
            logger = logging.getLogger(__name__)
            logger.warning(f"Error reaching HubSpot revoke endpoint: {e}")

        with scope(organizer=request.organizer):
            token.delete()
            OrganizerHubSpotSettings.objects.filter(organizer=request.organizer).update(
                sync_enabled=False
            )

            events_with_tokens = HubSpotOAuthToken.objects.filter(
                event__organizer=request.organizer
            ).values_list("event_id", flat=True)
            HubSpotEventSettings.objects.filter(
                event__organizer=request.organizer
            ).exclude(event_id__in=events_with_tokens).update(sync_enabled=False)

            AuditLog.objects.create(
                organizer=request.organizer,
                event=None,
                action=AuditAction.ORG_DISCONNECT,
                ip_address=get_client_ip(request),
            )

        messages.success(request, _("Successfully disconnected from HubSpot."))
        return redirect(settings_url)
