"""Read serializers for VMS API responses.

Enforces privacy controls: raw ID numbers are NEVER exposed, only masked IDs.
"""
from __future__ import annotations

from rest_framework import serializers

from modules.vms.models import (
    AuditLogEntry,
    BlacklistEntry,
    CheckInOutLog,
    DeclaredItem,
    EmergencyMuster,
    Gate,
    Incident,
    MusterRollCall,
    Notification,
    Vehicle,
    Visitor,
    VisitPass,
    VisitPolicy,
    VisitRequest,
    VisitVisitor,
    VisitZone,
    Zone,
)


class VisitorSerializer(serializers.ModelSerializer):
    class Meta:
        model = Visitor
        fields = [
            "id",
            "name",
            "phone",
            "email",
            "organisation",
            "photo_url",
            "id_type",
            "masked_id",
            "consent_given",
            "consent_version",
            "consent_timestamp",
            "is_anonymized",
            "created_at",
        ]
        read_only_fields = fields


class GateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Gate
        fields = ["id", "code", "name", "description", "is_active", "entry_allowed", "exit_allowed"]
        read_only_fields = fields


class ZoneSerializer(serializers.ModelSerializer):
    class Meta:
        model = Zone
        fields = ["id", "code", "name", "is_restricted", "max_capacity", "current_occupancy", "is_active"]
        read_only_fields = fields


class VisitPolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = VisitPolicy
        fields = [
            "id",
            "version",
            "is_active",
            "max_visit_duration_hours",
            "advance_booking_limit_days",
            "daily_host_visitor_cap",
            "walkin_host_timeout_minutes",
            "retention_period_days",
            "overstay_threshold_minutes",
            "require_second_approval_for_groups_above",
            "allow_recurring_visits",
            "updated_at",
        ]
        read_only_fields = fields


class VehicleSerializer(serializers.ModelSerializer):
    class Meta:
        model = Vehicle
        fields = ["id", "vehicle_type", "registration_number", "driver_name", "driver_contact", "parking_bay"]
        read_only_fields = fields


class DeclaredItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = DeclaredItem
        fields = ["id", "item_name", "serial_number", "category", "is_verified_in", "is_verified_out"]
        read_only_fields = fields


class VisitPassSerializer(serializers.ModelSerializer):
    visitor_name = serializers.CharField(source="visitor.name", read_only=True)
    masked_id = serializers.CharField(source="visitor.masked_id", read_only=True)

    class Meta:
        model = VisitPass
        fields = [
            "id",
            "token",
            "pass_type",
            "is_multi_entry",
            "valid_from",
            "valid_to",
            "status",
            "visitor_name",
            "masked_id",
            "issued_at",
        ]
        read_only_fields = fields


class VisitRequestVisitorLinkSerializer(serializers.ModelSerializer):
    visitor = VisitorSerializer(read_only=True)

    class Meta:
        model = VisitVisitor
        fields = ["id", "visitor", "is_primary", "status", "checked_in_at", "checked_out_at"]
        read_only_fields = fields


class VisitRequestZoneLinkSerializer(serializers.ModelSerializer):
    zone = ZoneSerializer(read_only=True)

    class Meta:
        model = VisitZone
        fields = ["id", "zone", "is_elevated", "elevated_until"]
        read_only_fields = fields


class ReadVisitRequestSerializer(serializers.ModelSerializer):
    visitors = VisitRequestVisitorLinkSerializer(many=True, read_only=True)
    permitted_zones = VisitRequestZoneLinkSerializer(many=True, read_only=True)
    vehicles = VehicleSerializer(many=True, read_only=True)
    declared_items = DeclaredItemSerializer(many=True, read_only=True)
    passes = VisitPassSerializer(many=True, read_only=True)

    class Meta:
        model = VisitRequest
        fields = [
            "id",
            "host_user_id",
            "purpose",
            "visit_type",
            "start_time",
            "end_time",
            "expected_duration_minutes",
            "status",
            "requires_second_approval",
            "rejection_reason",
            "host_decision_at",
            "second_decision_at",
            "created_at",
            "visitors",
            "permitted_zones",
            "vehicles",
            "declared_items",
            "passes",
        ]
        read_only_fields = fields


class CheckInOutLogSerializer(serializers.ModelSerializer):
    visitor_name = serializers.CharField(source="visitor.name", read_only=True)
    gate_name = serializers.CharField(source="gate.name", read_only=True)
    zone_name = serializers.CharField(source="zone.name", read_only=True, default=None)

    class Meta:
        model = CheckInOutLog
        fields = [
            "id",
            "pass_record",
            "visitor_name",
            "gate_name",
            "zone_name",
            "action",
            "guard_user_id",
            "timestamp",
            "is_manual_override",
            "override_reason",
            "notes",
        ]
        read_only_fields = fields


class BlacklistEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = BlacklistEntry
        fields = [
            "id",
            "name",
            "phone",
            "email",
            "id_type",
            "reason",
            "severity",
            "added_by_user_id",
            "expires_at",
            "is_active",
            "created_at",
        ]
        read_only_fields = ["id", "created_at"]


class IncidentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Incident
        fields = [
            "id",
            "request",
            "visitor",
            "severity",
            "category",
            "description",
            "reported_by_user_id",
            "status",
            "resolution_notes",
            "created_at",
            "resolved_at",
        ]
        read_only_fields = fields


class MusterRollCallSerializer(serializers.ModelSerializer):
    visitor_name = serializers.CharField(source="visitor.name", read_only=True)
    zone_name = serializers.CharField(source="zone.name", read_only=True, default=None)

    class Meta:
        model = MusterRollCall
        fields = ["id", "visitor", "visitor_name", "zone_name", "status", "marked_by_user_id", "marked_at", "notes"]
        read_only_fields = fields


class EmergencyMusterSerializer(serializers.ModelSerializer):
    records = MusterRollCallSerializer(many=True, read_only=True)

    class Meta:
        model = EmergencyMuster
        fields = [
            "id",
            "session_id",
            "status",
            "triggered_by_user_id",
            "triggered_at",
            "ended_at",
            "total_on_site",
            "safe_count",
            "unaccounted_count",
            "notes",
            "records",
        ]
        read_only_fields = fields


class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLogEntry
        fields = [
            "id",
            "who_user_id",
            "who_label",
            "action",
            "entity_type",
            "entity_id",
            "before_state",
            "after_state",
            "reason",
            "ip_address",
            "timestamp",
        ]
        read_only_fields = fields
