from rest_framework import serializers

from apps.makerspaces.models import Makerspace
from apps.printing.models import FilamentSpool, PrintBucket, PrintPrinter, PrintRequest
from apps.printing.serializers_buckets import ErrorSerializer, PrintBucketSerializer
from apps.printing.serializers_printers import PrintPrinterSerializer
from apps.printing.serializers_requests import (
    FailPrintSerializer,
    ManagedPrintRequestSerializer,
    PrintAcceptSerializer,
    PrintRequestCreateSerializer,
    PrintRequestSerializer,
    PrintStartSerializer,
    RejectFailSerializer,
)
from apps.printing.serializers_spools import (
    FilamentSpoolSerializer,
    FilamentSpoolSummarySerializer,
)

__all__ = [
    "ErrorSerializer",
    "FilamentSpool",
    "FailPrintSerializer",
    "FilamentSpoolSerializer",
    "FilamentSpoolSummarySerializer",
    "ManagedPrintRequestSerializer",
    "Makerspace",
    "PrintBucket",
    "PrintBucketSerializer",
    "PrintPrinter",
    "PrintPrinterSerializer",
    "PrintAcceptSerializer",
    "PrintRequest",
    "PrintRequestCreateSerializer",
    "PrintRequestSerializer",
    "PrintStartSerializer",
    "RejectFailSerializer",
    "serializers",
]
