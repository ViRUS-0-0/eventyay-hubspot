from django.utils.translation import gettext_lazy as _

from . import __version__

try:
    from eventyay.base.plugins import PluginConfig
except ImportError:
    raise RuntimeError("Please use a later version of eventyay")


class EventyayHubspotPluginApp(PluginConfig):
    default = True
    name = "hubspot"
    verbose_name = _("Eventyay Hubspot Plugin")

    class EventyayPluginMeta:
        name = _("Hubspot")
        author = "Om Vanwari"
        description = _("This plugin allows you to integrate Eventyay with Hubspot")
        visible = True
        version = __version__
        category = "INTEGRATION"

    def ready(self):
        from . import signals  # NOQA
