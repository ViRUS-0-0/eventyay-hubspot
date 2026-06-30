from django import forms
from django.utils.translation import gettext_lazy as _
from eventyay.base.models import Event
from eventyay.control.forms.filter import FilterForm
from eventyay.base.forms.widgets import DatePickerWidget

from .models import ObjectTypeMapping


class HubSpotLogFilterForm(FilterForm):
    type = forms.ChoiceField(
        label=_("Activity Type"),
        choices=(
            ("", _("All activity")),
            ("sync", _("Sync activity")),
            ("settings", _("Settings changes")),
        ),
        required=False,
    )
    query = forms.CharField(
        label=_("Search for..."),
        widget=forms.TextInput(
            attrs={"placeholder": _("Search for..."), "autofocus": "autofocus"}
        ),
        required=False,
    )
    date_from = forms.DateField(
        label=_("Date from"),
        required=False,
        widget=DatePickerWidget,
    )
    date_until = forms.DateField(
        label=_("Date until"),
        required=False,
        widget=DatePickerWidget,
    )


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
