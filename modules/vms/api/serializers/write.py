"""Write serializers for VMS request bodies."""
from __future__ import annotations

from rest_framework import serializers


class CompanionInputSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150)
    phone = serializers.CharField(max_length=20, required=False, default="")
    email = serializers.EmailField(required=False, default="")
    organisation = serializers.CharField(max_length=150, required=False, default="")
    id_type = serializers.CharField(max_length=30)
    id_number = serializers.CharField(max_length=50)


class VehicleInputSerializer(serializers.Serializer):
    vehicle_type = serializers.CharField(max_length=30, default="four_wheeler")
    registration_number = serializers.CharField(max_length=30)
    driver_name = serializers.CharField(max_length=100, required=False, default="")
    driver_contact = serializers.CharField(max_length=20, required=False, default="")
    parking_bay = serializers.CharField(max_length=50, required=False, default="")


class DeclaredItemInputSerializer(serializers.Serializer):
    item_name = serializers.CharField(max_length=150)
    serial_number = serializers.CharField(max_length=100, required=False, default="")
    category = serializers.CharField(max_length=30, default="other")


class WriteVisitRequestSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150)
    phone = serializers.CharField(max_length=20)
    email = serializers.EmailField(required=False, default="")
    organisation = serializers.CharField(max_length=150, required=False, default="")
    photo_url = serializers.CharField(max_length=500, required=False, default="")

    id_type = serializers.CharField(max_length=30)
    id_number = serializers.CharField(max_length=50)

    purpose = serializers.CharField(max_length=255)
    start_time = serializers.DateTimeField()
    end_time = serializers.DateTimeField()
    host_user_id = serializers.IntegerField(required=False)

    zone_ids = serializers.ListField(child=serializers.IntegerField(), required=False, default=list)
    companions = CompanionInputSerializer(many=True, required=False, default=list)
    vehicle = VehicleInputSerializer(required=False, allow_null=True, default=None)
    declared_items = DeclaredItemInputSerializer(many=True, required=False, default=list)

    consent_given = serializers.BooleanField(default=True)
    consent_version = serializers.CharField(max_length=20, default="v1.0")


class DecideVisitSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["approve", "reject"])
    reason = serializers.CharField(max_length=500, required=False, default="", allow_blank=True)


class CheckInSerializer(serializers.Serializer):
    pass_token = serializers.CharField(max_length=64)
    gate_id = serializers.IntegerField()
    zone_id = serializers.IntegerField(required=False, allow_null=True, default=None)
    override = serializers.BooleanField(default=False)
    override_reason = serializers.CharField(max_length=300, required=False, default="", allow_blank=True)


class CheckOutSerializer(serializers.Serializer):
    pass_token = serializers.CharField(max_length=64)
    gate_id = serializers.IntegerField()
    notes = serializers.CharField(max_length=300, required=False, default="", allow_blank=True)


class WalkinRegisterSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150)
    phone = serializers.CharField(max_length=20)
    email = serializers.EmailField(required=False, default="")
    id_type = serializers.CharField(max_length=30)
    id_number = serializers.CharField(max_length=50)
    photo_url = serializers.CharField(max_length=500, required=False, default="")

    purpose = serializers.CharField(max_length=255)
    host_user_id = serializers.IntegerField()
    duration_minutes = serializers.IntegerField(default=120)
    host_confirmed_verbally = serializers.BooleanField(default=True)


class ExtendVisitSerializer(serializers.Serializer):
    additional_minutes = serializers.IntegerField(min_value=15, max_value=480)
    reason = serializers.CharField(max_length=300, required=False, default="", allow_blank=True)


class CancelVisitSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=300, required=False, default="", allow_blank=True)


class MarkRollCallSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=["safe", "unaccounted", "evacuated"])
    notes = serializers.CharField(max_length=255, required=False, default="", allow_blank=True)


class TriggerMusterSerializer(serializers.Serializer):
    notes = serializers.CharField(max_length=300, required=False, default="", allow_blank=True)


class GateInputSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=50)
    name = serializers.CharField(max_length=100)
    description = serializers.CharField(max_length=255, required=False, default="")
    entry_allowed = serializers.BooleanField(default=True)
    exit_allowed = serializers.BooleanField(default=True)


class ZoneInputSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=50)
    name = serializers.CharField(max_length=100)
    is_restricted = serializers.BooleanField(default=False)
    max_capacity = serializers.IntegerField(default=0)


class BlacklistInputSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=150)
    phone = serializers.CharField(max_length=20, required=False, default="")
    email = serializers.EmailField(required=False, default="")
    id_type = serializers.CharField(max_length=30, required=False, default="")
    id_number = serializers.CharField(max_length=50, required=False, default="")
    reason = serializers.CharField()
    severity = serializers.ChoiceField(choices=["block", "watchlist"], default="block")
    expires_at = serializers.DateTimeField(required=False, allow_null=True, default=None)
