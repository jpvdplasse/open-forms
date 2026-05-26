from django.urls import path

from .views import DisclosureClaimsListView, DisclosuresListView, FlowClaimsView

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
    path(
        "flow-claims",
        FlowClaimsView.as_view(),
        name="flow-claims",
    ),
]
