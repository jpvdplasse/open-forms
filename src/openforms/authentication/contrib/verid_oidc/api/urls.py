from django.urls import path

from .views import DisclosureClaimsListView, DisclosuresListView

app_name = "authentication_verid"

urlpatterns = [
    path(
        "disclosures",
        DisclosuresListView.as_view(),
        name="disclosure-list",
    ),
    path(
        "disclosures/<uuid:uuid>/claims",
        DisclosureClaimsListView.as_view(),
        name="disclosure-claim-list",
    ),
]
