from rest_framework import serializers


class PrintingReportTotalsSerializer(serializers.Serializer):
    total_requests = serializers.IntegerField()
    completed = serializers.IntegerField()
    collected = serializers.IntegerField()
    failed = serializers.IntegerField()
    rejected = serializers.IntegerField()
    pending = serializers.IntegerField()
    printing = serializers.IntegerField()
    accepted = serializers.IntegerField()


class PrintingReportPrinterHoursSerializer(serializers.Serializer):
    printer_id = serializers.IntegerField()
    printer_name = serializers.CharField()
    completed_requests = serializers.IntegerField()
    hours = serializers.FloatField()
    makerspace_id = serializers.IntegerField(required=False)


class PrintingReportPrinterOutcomeSerializer(serializers.Serializer):
    printer_id = serializers.IntegerField()
    printer_name = serializers.CharField()
    completed = serializers.IntegerField()
    failed = serializers.IntegerField()
    grams_used = serializers.FloatField()
    manual_logs = serializers.IntegerField()
    makerspace_id = serializers.IntegerField(required=False)


class PrintingReportFilamentUsedSerializer(serializers.Serializer):
    spool_id = serializers.IntegerField()
    material = serializers.CharField()
    color = serializers.CharField(allow_blank=True)
    grams_used = serializers.FloatField()
    remaining_grams = serializers.FloatField()
    makerspace_id = serializers.IntegerField(required=False)


class PrintingReportPeriodSerializer(serializers.Serializer):
    period = serializers.CharField()
    grams = serializers.FloatField()


class PrintingReportPeriodsSerializer(serializers.Serializer):
    by_month = PrintingReportPeriodSerializer(many=True)
    by_day = PrintingReportPeriodSerializer(many=True)
    by_hour = PrintingReportPeriodSerializer(many=True)


class PrintingReportBrandSerializer(serializers.Serializer):
    brand = serializers.CharField()
    grams_used = serializers.FloatField()
    spools = serializers.IntegerField()


class PrintingReportTopRequesterSerializer(serializers.Serializer):
    requester_id = serializers.IntegerField()
    requester = serializers.CharField()
    requests = serializers.IntegerField()
    items = serializers.IntegerField()
    makerspace_id = serializers.IntegerField(required=False)


class PrintingReportPaymentsSerializer(serializers.Serializer):
    paid_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    paid_count = serializers.IntegerField()
    outstanding_amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    outstanding_count = serializers.IntegerField()


class PrintingReportSerializer(serializers.Serializer):
    totals = PrintingReportTotalsSerializer()
    printer_hours = PrintingReportPrinterHoursSerializer(many=True)
    printer_outcomes = PrintingReportPrinterOutcomeSerializer(many=True)
    filament_used = PrintingReportFilamentUsedSerializer(many=True)
    filament_by_brand = PrintingReportBrandSerializer(many=True)
    top_requesters = PrintingReportTopRequesterSerializer(many=True)
    total_grams_used = serializers.FloatField()
    payments = PrintingReportPaymentsSerializer()
    filament_estimated_by_period = PrintingReportPeriodsSerializer()
