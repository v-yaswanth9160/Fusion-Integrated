"""Views for Gate operations: QR verification, check-in, check-out, and walk-in registration."""
from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from fusion_auth.permissions import HasModuleGrant, HasPermission, IsAuthenticatedPrincipal
from modules.vms.api.serializers.read import (
    CheckInOutLogSerializer,
    ReadVisitRequestSerializer,
    VisitPassSerializer,
)
from modules.vms.api.serializers.write import (
    CheckInSerializer,
    CheckOutSerializer,
    WalkinRegisterSerializer,
)
from modules.vms.selectors.passes import get_pass_by_token
from modules.vms.selectors.visits import get_expected_today_visits
from modules.vms.services.visits import (
    check_in_visitor,
    check_out_visitor,
    register_walkin,
)


class GateVerifyPassView(APIView):
    """Scan and verify QR pass token without committing check-in."""
    permission_classes = [IsAuthenticatedPrincipal, HasModuleGrant("vms"), HasPermission("vms.pass.scan")]

    @extend_schema(responses={200: VisitPassSerializer})
    def post(self, request):
        token = request.data.get("token", "").strip()
        vpass = get_pass_by_token(token)
        return Response(VisitPassSerializer(vpass).data)


class GateCheckInView(APIView):
    """Guard checks in visitor upon physical arrival and QR scan."""
    permission_classes = [IsAuthenticatedPrincipal, HasModuleGrant("vms"), HasPermission("vms.gate.check_in_out")]

    @extend_schema(request=CheckInSerializer, responses={200: CheckInOutLogSerializer})
    def post(self, request):
        ser = CheckInSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        log = check_in_visitor(
            request.principal,
            pass_token=ser.validated_data["pass_token"],
            gate_id=ser.validated_data["gate_id"],
            zone_id=ser.validated_data.get("zone_id"),
            override=ser.validated_data.get("override", False),
            override_reason=ser.validated_data.get("override_reason", ""),
        )
        return Response(CheckInOutLogSerializer(log).data, status=status.HTTP_200_OK)


class GateCheckOutView(APIView):
    """Guard checks out visitor when exiting campus."""
    permission_classes = [IsAuthenticatedPrincipal, HasModuleGrant("vms"), HasPermission("vms.gate.check_in_out")]

    @extend_schema(request=CheckOutSerializer, responses={200: CheckInOutLogSerializer})
    def post(self, request):
        ser = CheckOutSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        log = check_out_visitor(
            request.principal,
            pass_token=ser.validated_data["pass_token"],
            gate_id=ser.validated_data["gate_id"],
            notes=ser.validated_data.get("notes", ""),
        )
        return Response(CheckInOutLogSerializer(log).data, status=status.HTTP_200_OK)


class GateWalkInView(APIView):
    """Register walk-in visitor at gate or reception."""
    permission_classes = [IsAuthenticatedPrincipal, HasModuleGrant("vms"), HasPermission("vms.walkin.register")]

    @extend_schema(request=WalkinRegisterSerializer, responses={201: ReadVisitRequestSerializer})
    def post(self, request):
        ser = WalkinRegisterSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        visit, vpass = register_walkin(request.principal, ser.validated_data)
        return Response(ReadVisitRequestSerializer(visit).data, status=status.HTTP_201_CREATED)


class GateExpectedTodayView(APIView):
    """List of today's expected and active visits for gate personnel."""
    permission_classes = [IsAuthenticatedPrincipal, HasModuleGrant("vms"), HasPermission("vms.pass.scan")]

    @extend_schema(responses={200: ReadVisitRequestSerializer(many=True)})
    def get(self, request):
        qs = get_expected_today_visits()
        return Response(ReadVisitRequestSerializer(qs, many=True).data)
