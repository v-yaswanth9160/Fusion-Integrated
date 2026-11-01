"""Public endpoints for external visitors without an institute account.

Allow unauthenticated access for self pre-registration, digital pass display, and cancellation.
"""
from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from fusion_auth.principal import Principal
from modules.vms.api.serializers.read import ReadVisitRequestSerializer, VisitPassSerializer
from modules.vms.api.serializers.write import CancelVisitSerializer, WriteVisitRequestSerializer
from modules.vms.selectors.passes import get_pass_by_token
from modules.vms.services.visits import cancel_visit_request, create_visit_request


class PublicRegisterView(APIView):
    """External visitor self pre-registration."""
    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    @extend_schema(request=WriteVisitRequestSerializer, responses={201: ReadVisitRequestSerializer})
    def post(self, request):
        ser = WriteVisitRequestSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        # Create a synthetic principal for the external visitor
        anon_principal = Principal(
            user_id=0,
            username="external_visitor",
            display_name=ser.validated_data["name"],
            kind="visitor",
            active_role="visitor",
            roles=("visitor",),
            permissions=frozenset(["vms.visit_request.create"]),
            modules=("vms",),
            email=ser.validated_data.get("email", ""),
        )

        visit = create_visit_request(anon_principal, ser.validated_data)
        return Response(ReadVisitRequestSerializer(visit).data, status=status.HTTP_201_CREATED)


class PublicPassView(APIView):
    """View digital pass and QR code details using unguessable token."""
    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    @extend_schema(responses={200: VisitPassSerializer})
    def get(self, request, token):
        vpass = get_pass_by_token(token)
        return Response(VisitPassSerializer(vpass).data)


class PublicCancelView(APIView):
    """Visitor cancels their own visit using unguessable pass token."""
    authentication_classes = []
    permission_classes = [permissions.AllowAny]

    @extend_schema(request=CancelVisitSerializer, responses={200: ReadVisitRequestSerializer})
    def post(self, request, token):
        vpass = get_pass_by_token(token)
        ser = CancelVisitSerializer(data=request.data)
        ser.is_valid(raise_exception=True)

        anon_principal = Principal(
            user_id=0,
            username="external_visitor",
            display_name=vpass.visitor.name,
            kind="visitor",
            active_role="visitor",
            roles=("visitor",),
            permissions=frozenset(["vms.visit_request.cancel"]),
            modules=("vms",),
            email=vpass.visitor.email,
        )

        cancelled = cancel_visit_request(anon_principal, vpass.request_id, reason=ser.validated_data.get("reason", ""))
        return Response(ReadVisitRequestSerializer(cancelled).data)
