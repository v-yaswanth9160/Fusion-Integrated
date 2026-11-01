"""Tests for VMS database models, constraints, and relationships."""
from datetime import timedelta
import pytest
from django.db import IntegrityError
from django.utils import timezone

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
    RecurringVisitSchedule,
    Vehicle,
    Visitor,
    VisitPass,
    VisitPolicy,
    VisitRequest,
    VisitVisitor,
    VisitZone,
    Zone,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def sample_visitor():
    return Visitor.objects.create(
        name="Vikram Singh",
        phone="9876543210",
        email="vikram@example.com",
        id_type="aadhaar",
        masked_id="XXXX-XXXX-1234",
        id_hash="dummy_hash_1234",
    )


@pytest.fixture
def sample_zone():
    return Zone.objects.create(code="ACAD", name="Academic Block", max_capacity=100)


@pytest.fixture
def sample_gate():
    return Gate.objects.create(code="MAIN", name="Main Gate")


@pytest.fixture
def sample_request():
    now = timezone.now()
    return VisitRequest.objects.create(
        host_user_id=101,
        purpose="Research Collaboration",
        start_time=now,
        end_time=now + timedelta(hours=2),
        expected_duration_minutes=120,
        status="draft",
    )


def test_visitor_creation_and_str(sample_visitor):
    assert str(sample_visitor) == "Vikram Singh (XXXX-XXXX-1234)"
    assert sample_visitor.consent_given is True
    assert sample_visitor.is_anonymized is False


def test_visit_policy_defaults():
    policy = VisitPolicy.objects.create(version=1)
    assert policy.max_visit_duration_hours == 8
    assert policy.walkin_host_timeout_minutes == 15
    assert policy.daily_host_visitor_cap == 10
    assert policy.is_active is True


def test_visit_request_end_time_must_be_after_start_time():
    now = timezone.now()
    with pytest.raises(IntegrityError):
        VisitRequest.objects.create(
            host_user_id=101,
            purpose="Invalid window",
            start_time=now,
            end_time=now - timedelta(hours=1),  # Inverted!
            expected_duration_minutes=60,
        )


def test_visit_request_positive_duration_constraint():
    now = timezone.now()
    with pytest.raises(IntegrityError):
        VisitRequest.objects.create(
            host_user_id=101,
            purpose="Zero duration",
            start_time=now,
            end_time=now + timedelta(hours=1),
            expected_duration_minutes=0,  # Must be > 0
        )


def test_visit_pass_validity_window_constraint(sample_request, sample_visitor):
    now = timezone.now()
    with pytest.raises(IntegrityError):
        VisitPass.objects.create(
            request=sample_request,
            visitor=sample_visitor,
            valid_from=now,
            valid_to=now - timedelta(minutes=10),  # Inverted!
            status="active",
        )


def test_zone_capacity_non_negative():
    with pytest.raises(IntegrityError):
        Zone.objects.create(
            code="INVALID",
            name="Negative Zone",
            max_capacity=50,
            current_occupancy=-1,
        )


def test_unique_together_visit_visitor(sample_request, sample_visitor):
    VisitVisitor.objects.create(request=sample_request, visitor=sample_visitor)
    with pytest.raises(IntegrityError):
        VisitVisitor.objects.create(request=sample_request, visitor=sample_visitor)


def test_unique_together_visit_zone(sample_request, sample_zone):
    VisitZone.objects.create(request=sample_request, zone=sample_zone)
    with pytest.raises(IntegrityError):
        VisitZone.objects.create(request=sample_request, zone=sample_zone)


def test_check_in_out_log_relationships(sample_request, sample_visitor, sample_gate, sample_zone):
    now = timezone.now()
    vpass = VisitPass.objects.create(
        request=sample_request,
        visitor=sample_visitor,
        valid_from=now,
        valid_to=now + timedelta(hours=4),
    )
    log = CheckInOutLog.objects.create(
        pass_record=vpass,
        visitor=sample_visitor,
        request=sample_request,
        gate=sample_gate,
        zone=sample_zone,
        action="check_in",
        guard_user_id=901,
    )
    assert log.action == "check_in"
    assert log.guard_user_id == 901
    assert log.pass_record == vpass


def test_declared_item_and_vehicle(sample_request):
    veh = Vehicle.objects.create(
        request=sample_request,
        vehicle_type="four_wheeler",
        registration_number="MP20-AB-1234",
    )
    item = DeclaredItem.objects.create(
        request=sample_request,
        item_name="MacBook Pro",
        serial_number="C02G1234XYZ",
        category="laptop",
    )
    assert veh.registration_number == "MP20-AB-1234"
    assert item.is_verified_in is False
    assert item.is_verified_out is False


def test_emergency_muster_and_roll_call(sample_request, sample_visitor, sample_zone):
    muster = EmergencyMuster.objects.create(
        triggered_by_user_id=901,
        total_on_site=1,
    )
    roll = MusterRollCall.objects.create(
        muster=muster,
        visitor=sample_visitor,
        request=sample_request,
        zone=sample_zone,
        status="unaccounted",
    )
    assert roll.status == "unaccounted"

    # Mark safe
    roll.status = "safe"
    roll.marked_by_user_id = 902
    roll.save()
    assert roll.status == "safe"


def test_blacklist_entry_and_query():
    bl = BlacklistEntry.objects.create(
        name="Malicious Actor",
        phone="9999999999",
        id_hash="bad_actor_hash",
        reason="Security trespass incident",
        added_by_user_id=901,
        severity="block",
    )
    assert bl.is_active is True
    assert BlacklistEntry.objects.filter(id_hash="bad_actor_hash", is_active=True).exists()


def test_audit_log_entry():
    entry = AuditLogEntry.objects.create(
        who_user_id=101,
        who_label="Prof. A Sharma",
        action="CREATE_VISIT",
        entity_type="VisitRequest",
        entity_id=1,
        after_state={"status": "draft"},
    )
    assert entry.action == "CREATE_VISIT"
    assert entry.after_state == {"status": "draft"}
