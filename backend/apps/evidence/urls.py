from django.urls import path

from apps.evidence.views import EvidenceDetailView, EvidenceUploadUrlView

app_name = "evidence_admin"

urlpatterns = [
    path(
        "makerspaces/<int:makerspace_id>/uploads/evidence-url",
        EvidenceUploadUrlView.as_view(),
        name="evidence-upload-url",
    ),
    path("evidence/<int:pk>", EvidenceDetailView.as_view(), name="evidence-detail"),
]
