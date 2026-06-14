from django.urls import path

from apps.procurement.views import (
    ToBuyDetailView,
    ToBuyExportView,
    ToBuyListCreateView,
)

app_name = "procurement"

urlpatterns = [
    path(
        "makerspace/<int:makerspace_id>/to-buy",
        ToBuyListCreateView.as_view(),
        name="to-buy-list",
    ),
    path(
        "makerspace/<int:makerspace_id>/to-buy/export",
        ToBuyExportView.as_view(),
        name="to-buy-export",
    ),
    path("to-buy/<int:pk>", ToBuyDetailView.as_view(), name="to-buy-detail"),
]
