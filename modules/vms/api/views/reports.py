"""Views for Reports, Export, and Audit trail."""
from __future__ import annotations

import csv
import io
from drf_spectacular.utils import extend_schema
from django.http import HttpResponse
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from fusion_auth.permissions import HasModuleGrant, HasPermission, IsAuthenticatedPrincipal
from modules.vms.api.serializers.read import (
    AuditLogSerializer,
    CheckInOutLogSerializer,
    IncidentSerializer,
    ReadVisitRequestSerializer,
)
from modules.vms.selectors.reports import (
    get_audit_trail,
    get_daily_logs,
    get_host_visit_summaries,
    get_overstay_incidents,
)
from modules.vms.services.audit import log_audit


class DailyReportView(APIView):
    permission_classes = [IsAuthenticatedPrincipal, HasModuleGrant("vms"), HasPermission("vms.report.view")]

    @extend_schema(responses={200: CheckInOutLogSerializer(many=True)})
    def get(self, request):
        logs = get_daily_logs()
        return Response(CheckInOutLogSerializer(logs[:100], many=True).data)


class OverstayReportView(APIView):
    permission_classes = [IsAuthenticatedPrincipal, HasModuleGrant("vms"), HasPermission("vms.report.view")]

    @extend_schema(responses={200: IncidentSerializer(many=True)})
    def get(self, request):
        incidents = get_overstay_incidents()
        return Response(IncidentSerializer(incidents, many=True).data)


class HostSummaryReportView(APIView):
    permission_classes = [IsAuthenticatedPrincipal, HasModuleGrant("vms"), HasPermission("vms.report.view")]

    def get(self, request):
        summaries = get_host_visit_summaries()
        return Response(summaries)


class AuditTrailView(APIView):
    permission_classes = [IsAuthenticatedPrincipal, HasModuleGrant("vms"), HasPermission("vms.audit.view")]

    @extend_schema(responses={200: AuditLogSerializer(many=True)})
    def get(self, request):
        entity = request.query_params.get("entity_type")
        logs = get_audit_trail(entity)
        return Response(AuditLogSerializer(logs[:200], many=True).data)


class ExportReportView(APIView):
    """Export operational logs to CSV, with mandatory audit tracking."""
    permission_classes = [IsAuthenticatedPrincipal, HasModuleGrant("vms"), HasPermission("vms.report.export")]

    def get(self, request):
        logs = get_daily_logs()

        # Audit the export action
        log_audit(
            who_user_id=request.principal.user_id,
            who_label=str(request.principal),
            action="EXPORT_VISITOR_REPORT",
            entity_type="Report",
            entity_id=0,
            reason="CSV Download",
        )

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="vms_daily_report.csv"'

        writer = csv.writer(response)
        writer.writerow(["Timestamp", "Visitor", "Action", "Gate", "Zone", "Guard ID", "Manual Override"])
        for log in logs[:500]:
            writer.writerow([
                log.timestamp.isoformat(),
                log.visitor.name,
                log.action,
                log.gate.name,
                log.zone.name if log.zone else "",
                log.guard_user_id,
                log.is_manual_override,
            ])
        return response
