"""Service and integration tests for VMS workflows A through H."""
from datetime import timedelta
import pytest
from django.utils import timezone

from conftest import make_principal
from modules.vms.domain.errors import (
    BlacklistMatchError,
    GuardFailedError,
    PassAlreadyUsedError,
    PassWindowInvalidError,
    SelfApprovalNotAllowedError,
    ZoneCapacityExceededError,
)
from modules.vms.models import (
    AuditLogEntry,
    BlacklistEntry,
    CheckInOutLog,
    EmergencyMuster,
    Gate,
    Incident,
    MusterRollCall,
    Notification,
    Visitor,
    VisitPass,
    VisitPolicy,
    VisitRequest,
    VisitVisitor,
    Zone,
)
from modules.vms.services.emergency import (
    end_emergency_muster,
    record_roll_call,
    trigger_emergency_muster,
)
from modules.vms.services.visits import (
    cancel_visit_request,
    check_in_visitor,
    check_out_visitor,
    create_visit_request,
    decide_visit_request,
    extend_visit_request,
    register_walkin,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def host_principal():
    return make_principal(
        user_id=101,
        kind="faculty",
        roles=("host", "faculty"),
        active_role="host",
        permissions=("vms.visit_request.create", "vms.visit_request.approve_host", "vms.visit_request.view_self"),
        modules=("vms",),
    )


@pytest.fixture
def approver_principal():
    return make_principal(
        user_id=201,
        kind="staff",
        roles=("dept_approver", "Dean Academic"),
        active_role="dept_approver",
        permissions=("vms.visit_request.approve_second_level", "vms.visit_request.view"),
        modules=("vms",),
    )


@pytest.fixture
def guard_principal():
    return make_principal(
        user_id=301,
        kind="staff",
        roles=("security_guard",),
        active_role="security_guard",
        permissions=("vms.pass.scan", "vms.gate.check_in_out", "vms.incident.report", "vms.emergency.roll_call"),
        modules=("vms",),
    )


@pytest.fixture
def reception_principal():
    return make_principal(
        user_id=401,
        kind="staff",
        roles=("reception",),
        active_role="reception",
        permissions=("vms.walkin.register", "vms.pass.issue", "vms.gate.check_in_out"),
        modules=("vms",),
    )


@pytest.fixture
def setup_campus():
    gate = Gate.objects.create(code="GATE_1", name="Main Gate")
    zone = Zone.objects.create(code="ACAD", name="Academic Block", max_capacity=5)
    policy = VisitPolicy.objects.create(version=1, is_active=True, max_visit_duration_hours=8, daily_host_visitor_cap=10)
    return {"gate": gate, "zone": zone, "policy": policy}


def test_workflow_a_pre_registered_visit_happy_path(host_principal, guard_principal, setup_campus):
    """Workflow A: Draft -> Pending Host Approval -> Approved -> Pass Issued -> Checked In -> Checked Out -> Completed."""
    now = timezone.now()
    start = now + timedelta(hours=1)
    end = now + timedelta(hours=3)

    req_data = {
        "name": "Dr. Ramesh Gupta",
        "phone": "9811122233",
        "email": "ramesh@example.com",
        "organisation": "IIT Bombay",
        "id_type": "aadhaar",
        "id_number": "1234-5678-9012",
        "purpose": "Academic Viva Committee",
        "start_time": start,
        "end_time": end,
        "host_user_id": 101,
        "zone_ids": [setup_campus["zone"].id],
    }

    # Step 1: Pre-registration
    req = create_visit_request(host_principal, req_data)
    assert req.status == "pending_host_approval"
    assert req.visitors.count() == 1
    visitor = req.visitors.first().visitor
    assert visitor.masked_id.endswith("9012")

    # Step 2: Host approves -> Pass Issued
    req = decide_visit_request(host_principal, req.id, action="approve")
    assert req.status == "pass_issued"
    vpass = VisitPass.objects.get(request=req)
    assert vpass.status == "active"
    assert vpass.token.startswith("VMS-")

    # Step 3: Guard checks in at gate
    # Set current time inside validity window
    vpass.valid_from = now - timedelta(minutes=10)
    vpass.valid_to = now + timedelta(hours=2)
    vpass.save()

    log_in = check_in_visitor(guard_principal, vpass.token, gate_id=setup_campus["gate"].id)
    assert log_in.action == "check_in"
    req.refresh_from_db()
    assert req.status == "on_site"

    # Zone capacity incremented
    setup_campus["zone"].refresh_from_db()
    assert setup_campus["zone"].current_occupancy == 1

    # Step 4: Guard checks out visitor -> Completed
    log_out = check_out_visitor(guard_principal, vpass.token, gate_id=setup_campus["gate"].id)
    assert log_out.action == "check_out"
    req.refresh_from_db()
    assert req.status == "completed"

    vpass.refresh_from_db()
    assert vpass.status == "completed"

    # Zone capacity decremented
    setup_campus["zone"].refresh_from_db()
    assert setup_campus["zone"].current_occupancy == 0


def test_workflow_b_rejection_requires_mandatory_justification(host_principal, setup_campus):
    """Workflow B: Rejection requires non-empty justification."""
    now = timezone.now()
    req = create_visit_request(
        host_principal,
        {
            "name": "Arun Kumar",
            "phone": "9822233344",
            "id_type": "pan",
            "id_number": "ABCDE1234F",
            "purpose": "Vendor Pitch",
            "start_time": now + timedelta(hours=2),
            "end_time": now + timedelta(hours=4),
            "host_user_id": 101,
        },
    )

    # Empty reason fails
    with pytest.raises(GuardFailedError):
        decide_visit_request(host_principal, req.id, action="reject", reason="")

    # Valid reason succeeds
    req = decide_visit_request(host_principal, req.id, action="reject", reason="Not available today.")
    assert req.status == "rejected"
    assert req.rejection_reason == "Not available today."


def test_workflow_b_cancellation_revokes_passes(host_principal, setup_campus):
    """Workflow B: Cancellation revokes any issued pass."""
    now = timezone.now()
    req = create_visit_request(
        host_principal,
        {
            "name": "Kiran Shah",
            "phone": "9833344455",
            "id_type": "driving_licence",
            "id_number": "DL12345678",
            "purpose": "Campus Tour",
            "start_time": now + timedelta(hours=2),
            "end_time": now + timedelta(hours=4),
            "host_user_id": 101,
        },
    )
    req = decide_visit_request(host_principal, req.id, action="approve")
    vpass = VisitPass.objects.get(request=req)
    assert vpass.status == "active"

    # Cancel
    cancel_visit_request(host_principal, req.id, reason="Plans changed.")
    req.refresh_from_db()
    assert req.status == "cancelled"

    vpass.refresh_from_db()
    assert vpass.status == "revoked"


def test_workflow_c_walk_in_registration_and_pass_issue(reception_principal, guard_principal, setup_campus):
    """Workflow C: Walk-in registered at gate by reception."""
    req, vpass = register_walkin(
        reception_principal,
        {
            "name": "Walkin Visitor",
            "phone": "9844455566",
            "id_type": "aadhaar",
            "id_number": "9999-8888-7777",
            "purpose": "Urgent Document Submission",
            "host_user_id": 101,
            "host_confirmed_verbally": True,
        },
    )
    assert req.visit_type == "walk_in"
    assert req.status == "pass_issued"
    assert vpass.status == "active"

    # Immediate check-in
    log = check_in_visitor(guard_principal, vpass.token, gate_id=setup_campus["gate"].id)
    assert log.action == "check_in"
    req.refresh_from_db()
    assert req.status == "on_site"


def test_workflow_f_blacklisted_person_blocked_and_incident_flagged(host_principal, setup_campus):
    """Workflow F: Blacklisted person is blocked at registration with an incident logged."""
    BlacklistEntry.objects.create(
        name="Known Offender",
        phone="9988776655",
        id_hash="dummy_hash",
        reason="Repeated security breaches",
        added_by_user_id=1,
        severity="block",
    )

    with pytest.raises(BlacklistMatchError) as exc_info:
        create_visit_request(
            host_principal,
            {
                "name": "Known Offender",
                "phone": "9988776655",  # Blacklisted phone
                "id_type": "aadhaar",
                "id_number": "1111-2222-3333",
                "purpose": "Meeting",
                "start_time": timezone.now() + timedelta(hours=1),
                "end_time": timezone.now() + timedelta(hours=2),
                "host_user_id": 101,
            },
        )
    assert "Repeated security breaches" in str(exc_info.value)

    # Incident was created
    inc = Incident.objects.filter(category="blacklist_attempt").first()
    assert inc is not None
    assert inc.severity == "critical"


def test_workflow_g_group_visit_with_multiple_companions(host_principal, guard_principal, setup_campus):
    """Workflow G: Group visit with multiple companions individually tracked."""
    now = timezone.now()
    req = create_visit_request(
        host_principal,
        {
            "name": "Team Leader",
            "phone": "9100011122",
            "id_type": "passport",
            "id_number": "TL123456",
            "purpose": "Team Project Review",
            "start_time": now + timedelta(hours=1),
            "end_time": now + timedelta(hours=3),
            "host_user_id": 101,
            "companions": [
                {"name": "Companion 1", "phone": "9100011123", "id_type": "passport", "id_number": "C1-111"},
                {"name": "Companion 2", "phone": "9100011124", "id_type": "passport", "id_number": "C2-222"},
            ],
        },
    )
    assert req.visitors.count() == 3
    assert req.visit_type == "group"

    req = decide_visit_request(host_principal, req.id, action="approve")
    assert req.passes.count() == 3

    # Check in companion 1 individually
    p1 = req.passes.first()
    p1.valid_from = now - timedelta(minutes=5)
    p1.valid_to = now + timedelta(hours=2)
    p1.save()

    check_in_visitor(guard_principal, p1.token, gate_id=setup_campus["gate"].id)
    link1 = VisitVisitor.objects.get(request=req, visitor=p1.visitor)
    assert link1.status == "on_site"


def test_workflow_h_emergency_muster_roll_call(host_principal, guard_principal, setup_campus):
    """Workflow H: Security triggers emergency muster, checks in/safe roll call."""
    now = timezone.now()
    # Check in a visitor
    req, vpass = register_walkin(
        guard_principal,
        {
            "name": "Onsite Guest",
            "phone": "9555566666",
            "id_type": "voter_id",
            "id_number": "VOTER-123",
            "purpose": "Inspection",
            "host_user_id": 101,
            "host_confirmed_verbally": True,
        },
    )
    vpass.valid_from = now - timedelta(minutes=5)
    vpass.valid_to = now + timedelta(hours=2)
    vpass.save()

    check_in_visitor(guard_principal, vpass.token, gate_id=setup_campus["gate"].id)

    # Trigger emergency muster
    muster = trigger_emergency_muster(guard_principal, notes="Fire alarm drill in academic zone")
    assert muster.status == "active"
    assert muster.total_on_site == 1
    assert muster.unaccounted_count == 1
    assert muster.safe_count == 0

    # Mark guest safe
    roll = record_roll_call(guard_principal, muster.id, vpass.visitor_id, status="safe", notes="Found at assembly point")
    assert roll.status == "safe"
    muster.refresh_from_db()
    assert muster.safe_count == 1
    assert muster.unaccounted_count == 0

    # End muster
    muster = end_emergency_muster(guard_principal, muster.id)
    assert muster.status == "completed"
    assert muster.ended_at is not None


def test_zone_capacity_limit_blocks_excess_checkin(guard_principal, setup_campus):
    """Negative test: zone capacity limit blocks check-in when full."""
    # Set capacity to 1
    setup_campus["zone"].max_capacity = 1
    setup_campus["zone"].current_occupancy = 1
    setup_campus["zone"].save()

    now = timezone.now()
    req, vpass = register_walkin(
        guard_principal,
        {
            "name": "Overflow Visitor",
            "phone": "9777788888",
            "id_type": "pan",
            "id_number": "PAN9999",
            "purpose": "Visit",
            "host_user_id": 101,
            "host_confirmed_verbally": True,
        },
    )
    vpass.valid_from = now - timedelta(minutes=5)
    vpass.valid_to = now + timedelta(hours=2)
    vpass.save()

    with pytest.raises(ZoneCapacityExceededError):
        check_in_visitor(guard_principal, vpass.token, gate_id=setup_campus["gate"].id, zone_id=setup_campus["zone"].id)


def test_pass_reuse_prevention(guard_principal, setup_campus):
    """Negative test: completed single-entry pass cannot be reused."""
    now = timezone.now()
    req, vpass = register_walkin(
        guard_principal,
        {
            "name": "One Time Guest",
            "phone": "9444433333",
            "id_type": "passport",
            "id_number": "PASS-ONETIME",
            "purpose": "One time meeting",
            "host_user_id": 101,
            "host_confirmed_verbally": True,
        },
    )
    vpass.valid_from = now - timedelta(minutes=5)
    vpass.valid_to = now + timedelta(hours=2)
    vpass.save()

    check_in_visitor(guard_principal, vpass.token, gate_id=setup_campus["gate"].id)
    check_out_visitor(guard_principal, vpass.token, gate_id=setup_campus["gate"].id)

    # Re-checkin must fail
    with pytest.raises(PassAlreadyUsedError):
        check_in_visitor(guard_principal, vpass.token, gate_id=setup_campus["gate"].id)
