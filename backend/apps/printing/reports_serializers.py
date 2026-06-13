from rest_framework import serializers


class PrintingReportTotalsSerializer(serializers.Serializer):
    total_requests = serializers.IntegerField()
    completed = serializers.IntegerField()
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


class PrintingReportSerializer(serializers.Serializer):
    totals = PrintingReportTotalsSerializer()
    printer_hours = PrintingReportPrinterHoursSerializer(many=True)
    filament_used = PrintingReportFilamentUsedSerializer(many=True)
    total_grams_used = serializers.FloatField()
    filament_estimated_by_period = PrintingReportPeriodsSerializer()
