from django import forms
from django.utils.translation import gettext_lazy as _
from eventyay.base.models import Event

from .models import ObjectTypeMapping


class ObjectTypeMappingForm(forms.ModelForm):
    class Meta:
        model = ObjectTypeMapping
        fields = ["eventyay_object_type", "hubspot_object_type", "position"]
        widgets = {
            "eventyay_object_type": forms.Select(attrs={"class": "form-control"}),
            "hubspot_object_type": forms.Select(attrs={"class": "form-control"}),
            "position": forms.HiddenInput(attrs={"class": "mapping-position"}),
        }


class BaseObjectTypeMappingFormSet(forms.BaseInlineFormSet):
    def clean(self):
        super().clean()
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


ObjectTypeMappingFormSet = forms.inlineformset_factory(
    parent_model=Event,
    model=ObjectTypeMapping,
    form=ObjectTypeMappingForm,
    formset=BaseObjectTypeMappingFormSet,
    fk_name="event",
    extra=0,
    can_delete=True,
)
