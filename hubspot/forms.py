from django import forms
from django.utils.translation import gettext_lazy as _
from eventyay.base.models import Event

from .models import ObjectTypeMapping, HubSpotFieldMapping, SyncMode


class ObjectTypeMappingForm(forms.ModelForm):
    class Meta:
        model = ObjectTypeMapping
        fields = ["eventyay_object_type", "hubspot_object_type", "position"]
        widgets = {
            "eventyay_object_type": forms.Select(attrs={"class": "form-control"}),
            "hubspot_object_type": forms.Select(attrs={"class": "form-control"}),
            "position": forms.HiddenInput(attrs={"class": "mapping-position"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if "position" in self.fields:
            self.fields["position"].required = False

    def clean_position(self):
        pos = self.cleaned_data.get("position")
        return pos if pos is not None else 0


class BaseObjectTypeMappingFormSet(forms.BaseInlineFormSet):
    def clean(self):
        seen = set()
        for form in self.forms:
            if self._should_delete_form(form):
                continue
            if not form.cleaned_data:
                continue
            pair = (
                form.cleaned_data.get("eventyay_object_type"),
                form.cleaned_data.get("hubspot_object_type"),
            )
            if not all(pair):
                continue
            if pair in seen:
                raise forms.ValidationError(
                    _(
                        "Duplicate mapping: each eventyay / HubSpot object-type "
                        "pair may only appear once per event."
                    )
                )
            seen.add(pair)
        super().clean()


ObjectTypeMappingFormSet = forms.inlineformset_factory(
    parent_model=Event,
    model=ObjectTypeMapping,
    form=ObjectTypeMappingForm,
    formset=BaseObjectTypeMappingFormSet,
    fk_name="event",
    extra=0,
    can_delete=True,
)


class HubSpotFieldMappingForm(forms.ModelForm):
    class Meta:
        model = HubSpotFieldMapping
        fields = ["eventyay_field", "hubspot_property", "sync_mode", "is_active"]

    def _calculate_warnings(self, eventyay_field, hubspot_property):
        warnings = []
        if eventyay_field and hubspot_property:
            ey_lower = eventyay_field.lower()
            hs_lower = hubspot_property.lower()

            # Heuristic 1: Boolean mapped to non-boolean
            ey_is_bool = any(x in ey_lower for x in ["is_", "has_", "allow_"])
            hs_is_bool = any(x in hs_lower for x in ["is_", "has_", "allow_"])

            # Heuristic 2: ID or number mapped to string
            ey_is_num = "id" in ey_lower or "count" in ey_lower
            hs_is_num = "id" in hs_lower or "count" in hs_lower

            if (ey_is_bool and not hs_is_bool) or (not ey_is_bool and hs_is_bool):
                warnings.append(
                    _(
                        "Warning: Possible type mismatch. Mapping a yes/no field to a different type."
                    )
                )
            elif (ey_is_num and not hs_is_num) or (not ey_is_num and hs_is_num):
                warnings.append(
                    _(
                        "Warning: Possible type mismatch. Mapping a number field to a different type."
                    )
                )
        return warnings

    def _build_choices(self, fields_list):
        grouped = {}
        for f in fields_list:
            cat = f.get("category", "Other")
            if cat not in grouped:
                grouped[cat] = []

            dt = f.get("data_type", "text")
            if dt == "text":
                dt_str = "Text (one line)"
            elif dt == "number":
                dt_str = "Number"
            elif dt == "yes/no":
                dt_str = "Yes/No"
            elif dt == "date":
                dt_str = "Date and time"
            elif dt == "country_code":
                dt_str = "Country code (ISO 3166-1 alpha-2)"
            else:
                dt_str = dt

            label = f"{f['label']} [{dt_str}]"
            grouped[cat].append((f["key"], label))

        choices = [("", "---------")]
        for cat, items in grouped.items():
            choices.append((cat, items))
        return choices

    def __init__(self, *args, **kwargs):
        eventyay_fields = kwargs.pop("eventyay_fields", [])
        hubspot_properties = kwargs.pop("hubspot_properties", [])
        super().__init__(*args, **kwargs)
        self.warnings = []

        ey_choices = self._build_choices(eventyay_fields)
        hs_choices = self._build_choices(hubspot_properties)

        self.fields["eventyay_field"].widget = forms.Select(choices=ey_choices)
        self.fields["hubspot_property"].widget = forms.Select(choices=hs_choices)

        for name, field in self.fields.items():
            if name != "is_active":
                field.widget.attrs["class"] = "form-control"
                if name in ("eventyay_field", "hubspot_property"):
                    field.widget.attrs["class"] += " select2-static"

        # Add a custom class for sync mode
        if "sync_mode" in self.fields:
            self.fields["sync_mode"].widget.attrs["class"] += " sync-mode-select"

        # Calculate warnings for initial data
        eventyay_field = self.initial.get("eventyay_field", "")
        if not eventyay_field and self.instance and self.instance.pk:
            eventyay_field = self.instance.eventyay_field

        hubspot_property = self.initial.get("hubspot_property", "")
        if not hubspot_property and self.instance and self.instance.pk:
            hubspot_property = self.instance.hubspot_property

        self.warnings = self._calculate_warnings(eventyay_field, hubspot_property)

    def clean(self):
        cleaned_data = super().clean()
        eventyay_field = cleaned_data.get("eventyay_field", "")
        hubspot_property = cleaned_data.get("hubspot_property", "")

        self.warnings = self._calculate_warnings(eventyay_field, hubspot_property)
        return cleaned_data


class BaseHubSpotFieldMappingFormSet(forms.BaseModelFormSet):
    def add_fields(self, form, index):
        super().add_fields(form, index)

        is_identifier = False
        if (
            form.instance
            and form.instance.pk
            and form.instance.sync_mode == SyncMode.IDENTIFIER
        ):
            is_identifier = True
        elif not self.initial_form_count() and index == 0:
            is_identifier = True

        if is_identifier:
            form.fields["sync_mode"].widget.choices = [
                (SyncMode.IDENTIFIER, _("Identifier"))
            ]
            form.fields["sync_mode"].widget.attrs["readonly"] = True
            form.fields["sync_mode"].widget.attrs[
                "style"
            ] = "pointer-events: none; background-color: #eee;"
            if not form.initial.get("sync_mode"):
                form.initial["sync_mode"] = SyncMode.IDENTIFIER
        else:
            choices = [
                c
                for c in form.fields["sync_mode"].choices
                if c[0] != SyncMode.IDENTIFIER
            ]
            form.fields["sync_mode"].widget.choices = choices
            if form.initial.get("sync_mode") == SyncMode.IDENTIFIER:
                form.initial["sync_mode"] = SyncMode.OVERWRITE

    def clean(self):
        super().clean()

        if any(self.errors):
            # Don't bother validating the formset if there are individual form errors
            return

        identifier_count = 0
        for form in self.forms:
            if self.can_delete and self._should_delete_form(form):
                continue

            sync_mode = form.cleaned_data.get("sync_mode")
            if sync_mode == SyncMode.IDENTIFIER:
                identifier_count += 1

        if identifier_count == 0:
            raise forms.ValidationError(
                _("Exactly one row must have its sync mode set to 'Identifier'."),
                code="missing_identifier",
            )
        elif identifier_count > 1:
            raise forms.ValidationError(
                _(
                    "Only one row can be set as 'Identifier'. You have selected %(count)d."
                ),
                params={"count": identifier_count},
                code="multiple_identifiers",
            )
