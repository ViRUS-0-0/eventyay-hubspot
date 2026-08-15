from pathlib import Path

from django.core.exceptions import ImproperlyConfigured
from django.utils.translation import gettext_lazy as _
from dotenv import load_dotenv

from . import __version__


try:
    from eventyay.base.plugins import PluginConfig
except ImportError as e:
    raise ImproperlyConfigured("Please use a later version of eventyay") from e


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
        from django.conf import settings

        plugin_dir = Path(__file__).resolve().parent.parent
        project_root = getattr(settings, "PROJECT_ROOT", plugin_dir)
        env_hubspot_path = plugin_dir / ".env.hubspot"
        eventyay_env_dev_path = project_root.parent / ".env.dev"
        eventyay_env_path = project_root.parent / ".env"

        if env_hubspot_path.exists():
            load_dotenv(dotenv_path=env_hubspot_path)
        elif eventyay_env_dev_path.exists():
            load_dotenv(dotenv_path=eventyay_env_dev_path)
        elif eventyay_env_path.exists():
            load_dotenv(dotenv_path=eventyay_env_path)
        elif (plugin_dir / ".env").exists():
            load_dotenv(dotenv_path=plugin_dir / ".env")
