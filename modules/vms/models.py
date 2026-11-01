"""VMS Database Models.

Zero cross-module ForeignKeys: foreign actors are integer user_ids.
PII protection: Government ID numbers are stored masked and as salted hashes.
"""
from datetime import timedelta
from django.db import models
from django.utils import timezone


class Visitor(models.Model):
    name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20, db_index=True)
    email = models.EmailField(blank=True, default="", db_index=True)
    organisation = models.CharField(max_length=150, blank=True, default="")
    photo_url = models.URLField(blank=True, default="")
    id_type = models.CharField(max_length=30, default="aadhaar")
    id_hash = models.CharField(max_length=64, db_index=True)
    masked_id = models.CharField(max_length=30)
    consent_given = models.BooleanField(default=False)
    consent_version = models.CharField(max_length=20, default="v1.0")
    consent_timestamp = models.DateTimeField(null=True, blank=True)
    is_anonymized = models.BooleanField(default=False, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "vms_visitor"
        indexes = [models.Index(fields=["phone", "is_anonymized"]), models.Index(fields=["id_hash"])]

    def __str__(self):
        return f"{self.name} ({self.masked_id})"


class Gate(models.Model):
    code = models.CharField(max_length=30, unique=True)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    entry_allowed = models.BooleanField(default=True)
    exit_allowed = models.BooleanField(default=True)

    class Meta:
        db_table = "vms_gate"

    def __str__(self):
        return f"{self.name} ({self.code})"


class Zone(models.Model):
    code = models.CharField(max_length=30, unique=True)
    name = models.CharField(max_length=100)
    is_restricted = models.BooleanField(default=False)
    max_capacity = models.PositiveIntegerField(default=100)
    current_occupancy = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "vms_zone"

    def __str__(self):
        return f"{self.name} ({'Restricted' if self.is_restricted else 'General'})"


class BlacklistEntry(models.Model):
    SEVERITY_CHOICES = [("block", "Block"), ("watchlist", "Watchlist")]
    name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20, blank=True, default="", db_index=True)
    email = models.EmailField(blank=True, default="")
    id_type = models.CharField(max_length=30, blank=True, default="")
    id_hash = models.CharField(max_length=64, blank=True, default="", db_index=True)
    reason = models.TextField()
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES, default="block")
    added_by_user_id = models.IntegerField()
    expires_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "vms_blacklist_entry"

    def __str__(self):
        return f"Blacklist: {self.name} ({self.severity})"


class VisitRequest(models.Model):
    STATUS_CHOICES = [
        ("draft", "Draft"), ("pending_host_approval", "Pending Host"),
        ("pending_second_approval", "Pending Second"), ("pending_admin_contingency", "Contingency"),
        ("approved", "Approved"), ("pass_issued", "Pass Issued"), ("on_site", "On Site"),
        ("completed", "Completed"), ("rejected", "Rejected"), ("cancelled", "Cancelled"),
        ("expired", "Expired"), ("overstay", "Overstay"),
    ]
    VISIT_TYPES = [("single", "Single"), ("group", "Group"), ("walk_in", "Walk-in"), ("recurring", "Recurring")]

    host_user_id = models.IntegerField(db_index=True)
    second_approver_user_id = models.IntegerField(null=True, blank=True)
    purpose = models.CharField(max_length=255)
    visit_type = models.CharField(max_length=30, choices=VISIT_TYPES, default="single")
    start_time = models.DateTimeField(db_index=True)
    end_time = models.DateTimeField(db_index=True)
    expected_duration_minutes = models.PositiveIntegerField(default=60)
    status = models.CharField(max_length=30, choices=STATUS_CHOICES, default="pending_host_approval", db_index=True)
    requires_second_approval = models.BooleanField(default=False)
    rejection_reason = models.TextField(blank=True, default="")
    host_decision_at = models.DateTimeField(null=True, blank=True)
    second_decision_at = models.DateTimeField(null=True, blank=True)
    version = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "vms_visit_request"
        constraints = [
            models.CheckConstraint(condition=models.Q(end_time__gt=models.F("start_time")), name="valid_visit_window")
        ]

    def __str__(self):
        return f"Visit #{self.id} for Host {self.host_user_id} ({self.status})"


class VisitVisitor(models.Model):
    request = models.ForeignKey(VisitRequest, on_delete=models.CASCADE, related_name="visitors")
    visitor = models.ForeignKey(Visitor, on_delete=models.PROTECT, related_name="visits")
    is_primary = models.BooleanField(default=True)
    status = models.CharField(max_length=30, default="pending")
    checked_in_at = models.DateTimeField(null=True, blank=True)
    checked_out_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "vms_visit_visitor"
        unique_together = [("request", "visitor")]


class VisitZone(models.Model):
    request = models.ForeignKey(VisitRequest, on_delete=models.CASCADE, related_name="permitted_zones")
    zone = models.ForeignKey(Zone, on_delete=models.PROTECT, related_name="permitted_visits")
    is_elevated = models.BooleanField(default=False)
    elevated_until = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "vms_visit_zone"
        unique_together = [("request", "zone")]


class Vehicle(models.Model):
    request = models.ForeignKey(VisitRequest, on_delete=models.CASCADE, related_name="vehicles")
    vehicle_type = models.CharField(max_length=30, default="car")
    registration_number = models.CharField(max_length=30)
    driver_name = models.CharField(max_length=150, blank=True, default="")
    driver_contact = models.CharField(max_length=20, blank=True, default="")
    parking_bay = models.CharField(max_length=50, blank=True, default="")

    class Meta:
        db_table = "vms_vehicle"


class DeclaredItem(models.Model):
    request = models.ForeignKey(VisitRequest, on_delete=models.CASCADE, related_name="declared_items")
    item_name = models.CharField(max_length=150)
    serial_number = models.CharField(max_length=100, blank=True, default="")
    category = models.CharField(max_length=50, default="laptop")
    is_verified_in = models.BooleanField(default=False)
    is_verified_out = models.BooleanField(default=False)

    class Meta:
        db_table = "vms_declared_item"


class VisitPass(models.Model):
    PASS_STATUS = [("active", "Active"), ("used", "Used"), ("expired", "Expired"), ("revoked", "Revoked"), ("completed", "Completed")]
    request = models.ForeignKey(VisitRequest, on_delete=models.CASCADE, related_name="passes")
    visitor = models.ForeignKey(Visitor, on_delete=models.PROTECT, related_name="passes")
    token = models.CharField(max_length=128, unique=True, db_index=True)
    pass_type = models.CharField(max_length=30, default="single")
    is_multi_entry = models.BooleanField(default=False)
    valid_from = models.DateTimeField()
    valid_to = models.DateTimeField()
    status = models.CharField(max_length=20, choices=PASS_STATUS, default="active", db_index=True)
    issued_by_user_id = models.IntegerField(null=True, blank=True)
    issued_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "vms_visit_pass"

    def __str__(self):
        return f"Pass {self.token[:8]} ({self.status})"


class CheckInOutLog(models.Model):
    ACTIONS = [("check_in", "Check In"), ("check_out", "Check Out")]
    pass_record = models.ForeignKey(VisitPass, on_delete=models.CASCADE, related_name="logs")
    visitor = models.ForeignKey(Visitor, on_delete=models.CASCADE, related_name="logs")
    request = models.ForeignKey(VisitRequest, on_delete=models.CASCADE, related_name="logs")
    gate = models.ForeignKey(Gate, on_delete=models.PROTECT, related_name="logs")
    zone = models.ForeignKey(Zone, on_delete=models.PROTECT, null=True, blank=True, related_name="logs")
    action = models.CharField(max_length=20, choices=ACTIONS)
    guard_user_id = models.IntegerField()
    timestamp = models.DateTimeField(default=timezone.now, db_index=True)
    is_manual_override = models.BooleanField(default=False)
    override_reason = models.TextField(blank=True, default="")
    notes = models.TextField(blank=True, default="")

    class Meta:
        db_table = "vms_check_in_out_log"
        ordering = ["-timestamp"]


class Incident(models.Model):
    SEVERITY = [("low", "Low"), ("medium", "Medium"), ("high", "High"), ("critical", "Critical")]
    request = models.ForeignKey(VisitRequest, on_delete=models.SET_NULL, null=True, blank=True)
    visitor = models.ForeignKey(Visitor, on_delete=models.SET_NULL, null=True, blank=True)
    severity = models.CharField(max_length=20, choices=SEVERITY, default="medium")
    category = models.CharField(max_length=50)
    description = models.TextField()
    reported_by_user_id = models.IntegerField()
    status = models.CharField(max_length=20, default="open")
    resolution_notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "vms_incident"


class EmergencyMuster(models.Model):
    session_id = models.CharField(max_length=64, unique=True)
    status = models.CharField(max_length=20, default="active")
    triggered_by_user_id = models.IntegerField()
    triggered_at = models.DateTimeField(auto_now_add=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    total_on_site = models.PositiveIntegerField(default=0)
    safe_count = models.PositiveIntegerField(default=0)
    unaccounted_count = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True, default="")

    class Meta:
        db_table = "vms_emergency_muster"


class MusterRollCall(models.Model):
    STATUS = [("safe", "Safe"), ("unaccounted", "Unaccounted"), ("evacuated", "Evacuated")]
    muster = models.ForeignKey(EmergencyMuster, on_delete=models.CASCADE, related_name="records")
    visitor = models.ForeignKey(Visitor, on_delete=models.CASCADE)
    visitor_name = models.CharField(max_length=150)
    zone_name = models.CharField(max_length=100, blank=True, default="")
    status = models.CharField(max_length=20, choices=STATUS, default="unaccounted")
    marked_by_user_id = models.IntegerField(null=True, blank=True)
    marked_at = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True, default="")

    class Meta:
        db_table = "vms_muster_roll_call"


class Notification(models.Model):
    recipient_user_id = models.IntegerField(null=True, blank=True)
    recipient_email = models.EmailField(blank=True, default="")
    subject = models.CharField(max_length=255)
    body = models.TextField()
    status = models.CharField(max_length=20, default="sent")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "vms_notification"


class AuditLogEntry(models.Model):
    who_user_id = models.IntegerField(null=True, blank=True)
    who_label = models.CharField(max_length=150)
    action = models.CharField(max_length=64)
    entity_type = models.CharField(max_length=64)
    entity_id = models.IntegerField()
    before_state = models.JSONField(default=dict)
    after_state = models.JSONField(default=dict)
    reason = models.TextField(blank=True, default="")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "vms_audit_log_entry"
        ordering = ["-timestamp"]


class RecurringVisitSchedule(models.Model):
    request = models.ForeignKey(VisitRequest, on_delete=models.CASCADE)
    cron_expression = models.CharField(max_length=64)
    start_date = models.DateField()
    end_date = models.DateField()
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "vms_recurring_visit_schedule"


class VisitPolicy(models.Model):
    version = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)
    max_visit_duration_hours = models.PositiveIntegerField(default=8)
    advance_booking_limit_days = models.PositiveIntegerField(default=30)
    daily_host_visitor_cap = models.PositiveIntegerField(default=10)
    walkin_host_timeout_minutes = models.PositiveIntegerField(default=15)
    retention_period_days = models.PositiveIntegerField(default=365)
    overstay_threshold_minutes = models.PositiveIntegerField(default=15)
    require_second_approval_for_groups_above = models.PositiveIntegerField(default=5)
    allow_recurring_visits = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "vms_visit_policy"

    def __str__(self):
        return f"VisitPolicy v{self.version} ({'active' if self.is_active else 'inactive'})"
