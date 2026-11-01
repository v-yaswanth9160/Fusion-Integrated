"""Views for Blacklist and Watchlist management."""
from __future__ import annotations

import hashlib
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from fusion_auth.permissions import HasModuleGrant, HasPermission, IsAuthenticatedPrincipal
from modules.vms.api.serializers.read import BlacklistEntrySerializer
from modules.vms.api.serializers.write import BlacklistInputSerializer
from modules.vms.models import BlacklistEntry
from modules.vms.services.audit import log_audit


class BlacklistListCreateView(APIView):
    permission_classes = [IsAuthenticatedPrincipal, HasModuleGrant("vms")]

    @extend_schema(responses={200: BlacklistEntrySerializer(many=True)})
    def get(self, request):
        if not request.principal.has_permission("vms.blacklist.view"):
            return Response({"error": {"code": "permission_denied", "message": "Permission denied"}}, status=status.HTTP_403_FORBIDDEN)
        entries = BlacklistEntry.objects.all().order_by("-created_at")
        return Response(BlacklistEntrySerializer(entries, many=True).data)

    @extend_schema(request=BlacklistInputSerializer, responses={201: BlacklistEntrySerializer})
    def post(self, request):
        if not request.principal.has_permission("vms.blacklist.manage"):
            return Response({"error": {"code": "permission_denied", "message": "Permission denied"}}, status=status.HTTP_403_FORBIDDEN)

        ser = BlacklistInputSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        data = ser.validated_data

        id_hash = ""
        if id_num := data.get("id_number"):
            id_hash = hashlib.sha256(id_num.strip().upper().encode("utf-8")).hexdigest()

        entry = BlacklistEntry.objects.create(
            name=data["name"],
            phone=data.get("phone", ""),
            email=data.get("email", ""),
            id_type=data.get("id_type", ""),
            id_hash=id_hash,
            reason=data["reason"],
            severity=data.get("severity", "block"),
            added_by_user_id=request.principal.user_id,
            expires_at=data.get("expires_at"),
            is_active=True,
        )

        log_audit(
            who_user_id=request.principal.user_id,
            who_label=str(request.principal),
            action="ADD_BLACKLIST_ENTRY",
            entity_type="BlacklistEntry",
            entity_id=entry.id,
            after_state={"name": entry.name, "severity": entry.severity},
            reason=entry.reason,
        )

        return Response(BlacklistEntrySerializer(entry).data, status=status.HTTP_201_CREATED)


class BlacklistToggleActiveView(APIView):
    permission_classes = [IsAuthenticatedPrincipal, HasModuleGrant("vms"), HasPermission("vms.blacklist.manage")]

    @extend_schema(responses={200: BlacklistEntrySerializer})
    def patch(self, request, pk):
        entry = BlacklistEntry.objects.get(id=pk)
        entry.is_active = not entry.is_active
        entry.save()

        log_audit(
            who_user_id=request.principal.user_id,
            who_label=str(request.principal),
            action="TOGGLE_BLACKLIST_ACTIVE",
            entity_type="BlacklistEntry",
            entity_id=entry.id,
            after_state={"is_active": entry.is_active},
        )
        return Response(BlacklistEntrySerializer(entry).data)
