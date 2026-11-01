"""Views for Emergency Muster and evacuation roll call."""
from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from fusion_auth.permissions import HasModuleGrant, HasPermission, IsAuthenticatedPrincipal
from modules.vms.api.serializers.read import EmergencyMusterSerializer, MusterRollCallSerializer
from modules.vms.api.serializers.write import MarkRollCallSerializer, TriggerMusterSerializer
from modules.vms.models import EmergencyMuster
from modules.vms.services.emergency import (
    end_emergency_muster,
    record_roll_call,
    trigger_emergency_muster,
)


class EmergencyMusterActiveView(APIView):
    """Get active muster session or recent muster status."""
    permission_classes = [IsAuthenticatedPrincipal, HasModuleGrant("vms")]

    @extend_schema(responses={200: EmergencyMusterSerializer})
    def get(self, request):
        muster = EmergencyMuster.objects.filter(status="active").order_by("-triggered_at").first()
        if not muster:
            # Return most recently completed
            muster = EmergencyMuster.objects.order_by("-triggered_at").first()
        if not muster:
            return Response({"active": False, "muster": None})
        return Response(EmergencyMusterSerializer(muster).data)


class EmergencyMusterTriggerView(APIView):
    """Trigger an emergency muster drill."""
    permission_classes = [IsAuthenticatedPrincipal, HasModuleGrant("vms"), HasPermission("vms.emergency.trigger")]

    @extend_schema(request=TriggerMusterSerializer, responses={201: EmergencyMusterSerializer})
    def post(self, request):
        ser = TriggerMusterSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        muster = trigger_emergency_muster(request.principal, notes=ser.validated_data.get("notes", ""))
        return Response(EmergencyMusterSerializer(muster).data, status=status.HTTP_201_CREATED)


class EmergencyMusterRollCallView(APIView):
    """Mark visitor status during emergency roll call."""
    permission_classes = [IsAuthenticatedPrincipal, HasModuleGrant("vms"), HasPermission("vms.emergency.roll_call")]

    @extend_schema(request=MarkRollCallSerializer, responses={200: MusterRollCallSerializer})
    def post(self, request, muster_id, visitor_id):
        ser = MarkRollCallSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        roll = record_roll_call(
            request.principal,
            muster_id=muster_id,
            visitor_id=visitor_id,
            status=ser.validated_data["status"],
            notes=ser.validated_data.get("notes", ""),
        )
        return Response(MusterRollCallSerializer(roll).data)


class EmergencyMusterEndView(APIView):
    """Conclude emergency muster drill."""
    permission_classes = [IsAuthenticatedPrincipal, HasModuleGrant("vms"), HasPermission("vms.emergency.trigger")]

    @extend_schema(responses={200: EmergencyMusterSerializer})
    def post(self, request, muster_id):
        muster = end_emergency_muster(request.principal, muster_id)
        return Response(EmergencyMusterSerializer(muster).data)
