"""Views for Gates, Zones, and Visit Policy configuration."""
from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from fusion_auth.permissions import HasModuleGrant, HasPermission, IsAuthenticatedPrincipal
from modules.vms.api.serializers.read import (
    GateSerializer,
    VisitPolicySerializer,
    ZoneSerializer,
)
from modules.vms.api.serializers.write import (
    GateInputSerializer,
    ZoneInputSerializer,
)
from modules.vms.models import Gate, VisitPolicy, Zone
from modules.vms.services.audit import log_audit
from modules.vms.services.visits import get_active_policy


class GateListCreateView(APIView):
    permission_classes = [IsAuthenticatedPrincipal, HasModuleGrant("vms")]

    @extend_schema(responses={200: GateSerializer(many=True)})
    def get(self, request):
        return Response(GateSerializer(Gate.objects.filter(is_active=True), many=True).data)

    @extend_schema(request=GateInputSerializer, responses={201: GateSerializer})
    def post(self, request):
        if not request.principal.has_permission("vms.gate.manage"):
            return Response({"error": {"code": "permission_denied", "message": "Permission denied"}}, status=status.HTTP_403_FORBIDDEN)
        ser = GateInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        gate = Gate.objects.create(**ser.validated_data)
        return Response(GateSerializer(gate).data, status=status.HTTP_201_CREATED)


class ZoneListCreateView(APIView):
    permission_classes = [IsAuthenticatedPrincipal, HasModuleGrant("vms")]

    @extend_schema(responses={200: ZoneSerializer(many=True)})
    def get(self, request):
        return Response(ZoneSerializer(Zone.objects.filter(is_active=True), many=True).data)

    @extend_schema(request=ZoneInputSerializer, responses={201: ZoneSerializer})
    def post(self, request):
        if not request.principal.has_permission("vms.zone.manage"):
            return Response({"error": {"code": "permission_denied", "message": "Permission denied"}}, status=status.HTTP_403_FORBIDDEN)
        ser = ZoneInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        zone = Zone.objects.create(**ser.validated_data)
        return Response(ZoneSerializer(zone).data, status=status.HTTP_201_CREATED)


class VisitPolicyView(APIView):
    permission_classes = [IsAuthenticatedPrincipal, HasModuleGrant("vms")]

    @extend_schema(responses={200: VisitPolicySerializer})
    def get(self, request):
        policy = get_active_policy()
        return Response(VisitPolicySerializer(policy).data)

    @extend_schema(request=VisitPolicySerializer, responses={200: VisitPolicySerializer})
    def put(self, request):
        if not request.principal.has_permission("vms.policy.manage"):
            return Response({"error": {"code": "permission_denied", "message": "Permission denied"}}, status=status.HTTP_403_FORBIDDEN)
        policy = get_active_policy()
        for field in [
            "max_visit_duration_hours",
            "advance_booking_limit_days",
            "daily_host_visitor_cap",
            "walkin_host_timeout_minutes",
            "retention_period_days",
            "overstay_threshold_minutes",
            "require_second_approval_for_groups_above",
        ]:
            if field in request.data:
                setattr(policy, field, int(request.data[field]))
        policy.save()

        log_audit(
            who_user_id=request.principal.user_id,
            who_label=str(request.principal),
            action="UPDATE_VISIT_POLICY",
            entity_type="VisitPolicy",
            entity_id=policy.id,
            after_state=VisitPolicySerializer(policy).data,
        )
        return Response(VisitPolicySerializer(policy).data)
