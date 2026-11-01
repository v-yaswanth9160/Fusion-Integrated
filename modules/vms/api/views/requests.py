"""Views for authenticated visit requests, approvals, cancellations, and extensions."""
from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from fusion_auth.permissions import HasModuleGrant, HasPermission, IsAuthenticatedPrincipal
from modules.vms.api.serializers.read import ReadVisitRequestSerializer
from modules.vms.api.serializers.write import (
    CancelVisitSerializer,
    DecideVisitSerializer,
    ExtendVisitSerializer,
    WriteVisitRequestSerializer,
)
from modules.vms.selectors.visits import (
    get_visit_request_for_principal,
    visible_visit_requests,
)
from modules.vms.services.visits import (
    cancel_visit_request,
    create_visit_request,
    decide_visit_request,
    extend_visit_request,
)


class VisitRequestListCreateView(APIView):
    permission_classes = [IsAuthenticatedPrincipal, HasModuleGrant("vms")]

    @extend_schema(responses={200: ReadVisitRequestSerializer(many=True)})
    def get(self, request):
        qs = visible_visit_requests(request.principal)
        return Response(ReadVisitRequestSerializer(qs, many=True).data)

    @extend_schema(request=WriteVisitRequestSerializer, responses={201: ReadVisitRequestSerializer})
    def post(self, request):
        if not request.principal.has_permission("vms.visit_request.create"):
            return Response({"error": {"code": "permission_denied", "message": "Permission denied"}}, status=status.HTTP_403_FORBIDDEN)
        ser = WriteVisitRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        visit = create_visit_request(request.principal, ser.validated_data)
        return Response(ReadVisitRequestSerializer(visit).data, status=status.HTTP_201_CREATED)


class VisitRequestDetailView(APIView):
    permission_classes = [IsAuthenticatedPrincipal, HasModuleGrant("vms")]

    @extend_schema(responses={200: ReadVisitRequestSerializer})
    def get(self, request, pk):
        req = get_visit_request_for_principal(request.principal, pk)
        return Response(ReadVisitRequestSerializer(req).data)


class VisitRequestDecideView(APIView):
    """Host or Department Approver decision on visit request."""
    permission_classes = [IsAuthenticatedPrincipal, HasModuleGrant("vms")]

    @extend_schema(request=DecideVisitSerializer, responses={200: ReadVisitRequestSerializer})
    def post(self, request, pk):
        if not request.principal.has_any_permission("vms.visit_request.approve_host", "vms.visit_request.approve_second_level"):
            return Response({"error": {"code": "permission_denied", "message": "Permission denied"}}, status=status.HTTP_403_FORBIDDEN)

        ser = DecideVisitSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        decided = decide_visit_request(
            request.principal,
            pk,
            action=ser.validated_data["action"],
            reason=ser.validated_data.get("reason", ""),
        )
        return Response(ReadVisitRequestSerializer(decided).data)


class VisitRequestCancelView(APIView):
    """Cancel visit request prior to check-in."""
    permission_classes = [IsAuthenticatedPrincipal, HasModuleGrant("vms")]

    @extend_schema(request=CancelVisitSerializer, responses={200: ReadVisitRequestSerializer})
    def post(self, request, pk):
        if not request.principal.has_permission("vms.visit_request.cancel"):
            return Response({"error": {"code": "permission_denied", "message": "Permission denied"}}, status=status.HTTP_403_FORBIDDEN)

        ser = CancelVisitSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        cancelled = cancel_visit_request(request.principal, pk, reason=ser.validated_data.get("reason", ""))
        return Response(ReadVisitRequestSerializer(cancelled).data)


class VisitRequestExtendView(APIView):
    """Extend duration of an active or pending visit."""
    permission_classes = [IsAuthenticatedPrincipal, HasModuleGrant("vms")]

    @extend_schema(request=ExtendVisitSerializer, responses={200: ReadVisitRequestSerializer})
    def post(self, request, pk):
        if not request.principal.has_permission("vms.visit_request.extend"):
            return Response({"error": {"code": "permission_denied", "message": "Permission denied"}}, status=status.HTTP_403_FORBIDDEN)

        ser = ExtendVisitSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        extended = extend_visit_request(
            request.principal,
            pk,
            additional_minutes=ser.validated_data["additional_minutes"],
            reason=ser.validated_data.get("reason", ""),
        )
        return Response(ReadVisitRequestSerializer(extended).data)
