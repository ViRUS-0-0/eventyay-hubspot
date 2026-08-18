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
        import logging

        logger = logging.getLogger(__name__)

        plugin_dir = Path(__file__).resolve().parent.parent
        project_root = getattr(settings, "PROJECT_ROOT", plugin_dir)
        env_paths = [
            plugin_dir / ".env.hubspot",
            project_root / ".env",
            Path.cwd() / ".env",
            project_root.parent / ".env.dev",
            project_root.parent / ".env",
            plugin_dir / ".env",
        ]

        env_loaded = False
        for env_path in env_paths:
            if env_path.exists():
                load_dotenv(dotenv_path=env_path)
                logger.info(f"HubSpot plugin loaded environment variables from: {env_path}")
                env_loaded = True

        if not env_loaded:
            logger.error("HubSpot plugin: No .env file found.")
