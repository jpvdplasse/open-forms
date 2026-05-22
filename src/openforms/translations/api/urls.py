from django.http import JsonResponse
from django.urls import path
from django.views import View

from .views import (
    CustomizedCompiledTranslations,
    FormioTranslationsView,
    LanguageInfoView,
    SetLanguageView,
)


class FormioTranslationsStub(View):
    """Stub for SDK 3.5.0 which expects /api/v2/i18n/formio/<lang>.

    Returns an empty translation map so the SDK falls back to its bundled
    translations. Replace with a real implementation if/when the backend
    ships customized Formio translations again.
    """

    def get(self, request, language_code):
        return JsonResponse({})


app_name = "i18n"

urlpatterns = [
    path("info", LanguageInfoView.as_view(), name="info"),
    path("language", SetLanguageView.as_view(), name="language"),
    path(
        "formio/<str:language>",
        FormioTranslationsView.as_view(),
        name="formio-translations",
    ),
    path(
        "compiled-messages/<str:language_code>.json",
        CustomizedCompiledTranslations.as_view(),
        name="customized-translations",
    ),
    path(
        "formio/<str:language_code>",
        FormioTranslationsStub.as_view(),
        name="formio-translations-stub",
    ),
]
