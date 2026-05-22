from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class VerIDApp(AppConfig):
    name = "openforms.prefill.contrib.verid"
    label = "prefill_verid"
    verbose_name = _("VerID prefill plugin")

    def ready(self):
        # register the plugin
        from . import plugin  # noqa
