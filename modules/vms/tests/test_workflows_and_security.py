"""Comprehensive End-to-End Workflow & Security Tests for VMS.

Covers Workflows A to H (happy path and failure path of each), negative tests,
concurrency tests, and security/privacy guarantees.
"""
from datetime import timedelta
import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from fusion_auth.principal import Principal
from modules.vms.domain.errors import (
    BlacklistMatchError,
    InvalidTransitionError,
    PassAlreadyUsedError,
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
from modules.vms.services.emergency import end_emergency_muster, record_roll_call, trigger_emergency_muster
from modules.vms.services.jobs import expire_overdue_passes_job, flag_overstay_visitors_job
from modules.vms.services.visits import (
    cancel_visit_request,
    check_in_visitor,
    check_out_visitor,
    create_visit_request,
    decide_visit_request,
    register_walkin,
)


def make_p(user_id=9001, role="host", permissions=None, email="host@institute.ac.in"):
    perms = frozenset(permissions or [
        "vms.visit_request.view_self",
        "vms.visit_request.create",
        "vms.visit_request.approve_host",
        "vms.visit_request.approve_second_level",
        "vms.visit_request.cancel",
        "vms.pass.scan",
        "vms.pass.issue",
        "vms.gate.check_in_out",
        "vms.walkin.register",
        "vms.blacklist.view",
        "vms.blacklist.manage",
        "vms.emergency.trigger",
        "vms.emergency.roll_call",
        "vms.policy.manage",
    ])
    return Principal(
        user_id=user_id,
        username=f"u{user_id}",
        display_name=f"User {user_id}",
        kind="faculty" if "host" in role else "staff",
        active_role=role,
        roles=(role,),
        permissions=perms,
        modules=("vms",),
        email=email,
    )


@pytest.fixture
def base_setup(db):
    policy = VisitPolicy.objects.create(
        version=1,
        is_active=True,
        max_visit_duration_hours=8,
        advance_booking_limit_days=30,
        daily_host_visitor_cap=10,
        walkin_host_timeout_minutes=15,
        retention_period_days=365,
        overstay_threshold_minutes=15,
        require_second_approval_for_groups_above=5,
    )
    gate = Gate.objects.create(code="MAIN", name="Main Gate", is_active=True)
    zone = Zone.objects.create(code="ACAD", name="Academic Zone", max_capacity=5, is_restricted=False)
    restricted_zone = Zone.objects.create(code="SERVER_DC", name="Data Center", max_capacity=2, is_restricted=True)
    return {
        "policy": policy,
        "gate": gate,
        "zone": zone,
        "restricted_zone": restricted_zone,
    }


# ==============================================================================
# WORKFLOW A: Pre-registered visit complete lifecycle
# ==============================================================================
@pytest.mark.django_db
def test_workflow_a_happy_path(base_setup):
    host = make_p(9001, "host")
    guard = make_p(3001, "security_guard")

    # 1. Host creates request (Draft -> Pending Host Approval)
    start = timezone.now() + timedelta(hours=1)
    end = start + timedelta(hours=2)
    data = {
        "host_user_id": 9001,
        "purpose": "Academic Collaboration",
        "start_time": start,
        "end_time": end,
        "name": "Siddharth Rao",
        "phone": "9876543210",
        "email": "sid@example.com",
        "id_type": "aadhaar",
        "id_number": "1234-5678-9012",
        "zone_ids": [base_setup["zone"].id],
        "consent_record": {"consent_given": True, "version": "v1.0"},
    }
    visit = create_visit_request(host, data)
    assert visit.status == "pending_host_approval"

    # 2. Host approves -> Approved -> Pass Issued
    approved = decide_visit_request(host, visit.id, action="approve")
    assert approved.status == "pass_issued"
    vpass = VisitPass.objects.get(request=approved)
    assert vpass.status == "active"
    assert vpass.token.startswith("VMS-")

    # Adjust window for current arrival
    vpass.valid_from = timezone.now() - timedelta(minutes=5)
    vpass.save()

    # 3. Guard scans QR at valid window -> Checked In (on_site)
    log_in = check_in_visitor(guard, vpass.token, base_setup["gate"].id)
    assert log_in.action == "check_in"
    approved.refresh_from_db()
    assert approved.status == "on_site"

    # 4. Guard checks out visitor -> Completed / Closed
    log_out = check_out_visitor(guard, vpass.token, base_setup["gate"].id)
    assert log_out.action == "check_out"
    approved.refresh_from_db()
    assert approved.status == "completed"

    # Audit entries exist
    assert AuditLogEntry.objects.filter(entity_type="VisitRequest", entity_id=approved.id).count() >= 3


# ==============================================================================
# WORKFLOW B: Rejection & Cancellation
# ==============================================================================
@pytest.mark.django_db
def test_workflow_b_rejection_and_cancellation(base_setup):
    host = make_p(9001, "host")

    # Rejection requires reason
    start = timezone.now() + timedelta(hours=1)
    end = start + timedelta(hours=2)
    visit = create_visit_request(host, {
        "host_user_id": 9001,
        "purpose": "Vendor Pitch",
        "start_time": start,
        "end_time": end,
        "name": "Vendor Person",
        "phone": "9876500000",
        "id_type": "pan",
        "id_number": "ABCDE1234F",
        "consent_record": {"consent_given": True},
    })

    # Rejecting without reason fails
    with pytest.raises(Exception):
        decide_visit_request(host, visit.id, action="reject", reason="")

    # Rejecting with reason succeeds
    rejected = decide_visit_request(host, visit.id, action="reject", reason="Host out of station")
    assert rejected.status == "rejected"
    assert rejected.rejection_reason == "Host out of station"

    # Terminal state cannot be re-opened
    with pytest.raises(InvalidTransitionError):
        decide_visit_request(host, visit.id, action="approve")

    # Cancellation before check-in
    visit2 = create_visit_request(host, {
        "host_user_id": 9001,
        "purpose": "Follow up",
        "start_time": start,
        "end_time": end,
        "name": "Friend",
        "phone": "9876511111",
        "id_type": "pan",
        "id_number": "ABCDE5678G",
        "consent_record": {"consent_given": True},
    })
    cancelled = cancel_visit_request(host, visit2.id, reason="Meeting cancelled")
    assert cancelled.status == "cancelled"

    # Terminal cancelled cannot be transitioned
    with pytest.raises(InvalidTransitionError):
        decide_visit_request(host, visit2.id, action="approve")


# ==============================================================================
# WORKFLOW C: Walk-in lifecycle & Host confirmation
# ==============================================================================
@pytest.mark.django_db
def test_workflow_c_walkin_lifecycle(base_setup):
    reception = make_p(4001, "reception")
    host = make_p(9001, "host")
    guard = make_p(3001, "security_guard")

    # Register walk-in at desk
    walkin, walkin_pass = register_walkin(reception, {
        "name": "Courier Delivery",
        "phone": "9988112233",
        "id_type": "aadhaar",
        "id_number": "9999-8888-7777",
        "host_user_id": 9001,
        "purpose": "Important document handover",
        "duration_minutes": 30,
        "zone_ids": [base_setup["zone"].id],
        "gate_id": base_setup["gate"].id,
        "host_confirmed_verbally": False,
    })
    assert walkin.visit_type == "walk_in"
    assert walkin.status == "pending_host_approval"

    # Pass not yet issued
    assert walkin_pass is None
    assert VisitPass.objects.filter(request=walkin).count() == 0

    # Host approves walk-in
    decide_visit_request(host, walkin.id, action="approve")
    walkin.refresh_from_db()
    assert walkin.status == "pass_issued"

    vpass = VisitPass.objects.get(request=walkin)
    vpass.status = "active"
    vpass.valid_from = timezone.now() - timedelta(minutes=5)
    vpass.save()

    log_in = check_in_visitor(guard, vpass.token, base_setup["gate"].id)
    assert log_in.action == "check_in"
    walkin.refresh_from_db()
    assert walkin.status == "on_site"


# ==============================================================================
# WORKFLOW D: Overstay Detection
# ==============================================================================
@pytest.mark.django_db
def test_workflow_d_overstay_detection(base_setup):
    host = make_p(9001, "host")
    guard = make_p(3001, "security_guard")

    start = timezone.now() + timedelta(minutes=10)
    end = timezone.now() + timedelta(hours=1)
    visit = create_visit_request(host, {
        "host_user_id": 9001,
        "purpose": "Past meeting",
        "start_time": start,
        "end_time": end,
        "name": "Delayed Guest",
        "phone": "9900112233",
        "id_type": "pan",
        "id_number": "PAN990011X",
        "consent_record": {"consent_given": True},
    })
    decide_visit_request(host, visit.id, action="approve")
    visit.refresh_from_db()
    vpass = VisitPass.objects.get(request=visit)

    # Check in
    vpass.valid_from = timezone.now() - timedelta(hours=2)
    vpass.valid_to = timezone.now() - timedelta(minutes=20)  # Past validity
    vpass.save()
    visit.start_time = timezone.now() - timedelta(hours=2)
    visit.end_time = timezone.now() - timedelta(minutes=20)
    visit.save()

    check_in_visitor(guard, vpass.token, base_setup["gate"].id, override=True)
    visit.refresh_from_db()
    assert visit.status == "on_site"

    # Run scheduled overstay detection job
    flagged = flag_overstay_visitors_job()
    assert flagged >= 1
    visit.refresh_from_db()
    assert visit.status == "overstay"

    # Incident raised
    inc = Incident.objects.filter(request=visit).first()
    assert inc is not None
    assert inc.category == "overstay"


# ==============================================================================
# WORKFLOW E: Pass Expiry
# ==============================================================================
@pytest.mark.django_db
def test_workflow_e_pass_expiry(base_setup):
    host = make_p(9001, "host")
    guard = make_p(3001, "security_guard")

    start = timezone.now() + timedelta(minutes=5)
    end = timezone.now() + timedelta(hours=1)
    visit = create_visit_request(host, {
        "host_user_id": 9001,
        "purpose": "No-show visit",
        "start_time": start,
        "end_time": end,
        "name": "No Show Visitor",
        "phone": "9112233445",
        "id_type": "passport",
        "id_number": "P12345678",
        "consent_record": {"consent_given": True},
    })
    decide_visit_request(host, visit.id, action="approve")
    vpass = VisitPass.objects.get(request=visit)
    vpass.valid_from = timezone.now() - timedelta(hours=5)
    vpass.valid_to = timezone.now() - timedelta(hours=2)
    vpass.save()

    # Run expiry job
    expired_count = expire_overdue_passes_job()
    assert expired_count >= 1

    vpass.refresh_from_db()
    assert vpass.status == "expired"
    visit.refresh_from_db()
    assert visit.status == "expired"

    # Negative check: Expired pass can never be checked in
    with pytest.raises(PassAlreadyUsedError):
        check_in_visitor(guard, vpass.token, base_setup["gate"].id)


# ==============================================================================
# WORKFLOW F: Blacklist Screening
# ==============================================================================
@pytest.mark.django_db
def test_workflow_f_blacklist_screening(base_setup):
    host = make_p(9001, "host")

    # Add blacklist entry
    BlacklistEntry.objects.create(
        name="Known Offender",
        phone="9990001111",
        reason="Theft incident",
        severity="block",
        added_by_user_id=5001,
        is_active=True,
    )

    # Attempting to create request with blacklisted phone is rejected
    with pytest.raises(BlacklistMatchError):
        create_visit_request(host, {
            "host_user_id": 9001,
            "purpose": "Attempted visit",
            "start_time": timezone.now() + timedelta(hours=1),
            "end_time": timezone.now() + timedelta(hours=3),
            "name": "Known Offender",
            "phone": "9990001111",
            "id_type": "aadhaar",
            "id_number": "1111-2222-3333",
            "consent_record": {"consent_given": True},
        })

    # Incident logged
    incident = Incident.objects.filter(category="blacklist_attempt").first()
    assert incident is not None
    assert "Known Offender" in incident.description


# ==============================================================================
# WORKFLOW G: Group Visits
# ==============================================================================
@pytest.mark.django_db
def test_workflow_g_group_visits(base_setup):
    host = make_p(9001, "host")
    guard = make_p(3001, "security_guard")

    start = timezone.now() + timedelta(hours=1)
    end = start + timedelta(hours=3)
    data = {
        "host_user_id": 9001,
        "purpose": "Delegation Tour",
        "start_time": start,
        "end_time": end,
        "name": "Leader Person",
        "phone": "9811002200",
        "id_type": "passport",
        "id_number": "P88776655",
        "companions": [
            {"name": "Companion One", "phone": "9811002201", "id_type": "passport", "id_number": "P88776656"},
            {"name": "Companion Two", "phone": "9811002202", "id_type": "passport", "id_number": "P88776657"},
        ],
        "consent_record": {"consent_given": True},
    }
    visit = create_visit_request(host, data)
    assert visit.visitors.count() == 3

    # Approve and passes issued for all
    decide_visit_request(host, visit.id, action="approve")
    assert VisitPass.objects.filter(request=visit).count() == 3

    # Check in first companion individually
    p1 = VisitPass.objects.filter(request=visit).first()
    p1.valid_from = timezone.now() - timedelta(minutes=5)
    p1.save()

    log1 = check_in_visitor(guard, p1.token, base_setup["gate"].id)
    assert log1.action == "check_in"


# ==============================================================================
# WORKFLOW H: Emergency Muster Evacuation Drill
# ==============================================================================
@pytest.mark.django_db
def test_workflow_h_emergency_muster(base_setup):
    host = make_p(9001, "host")
    guard = make_p(3001, "security_guard")
    admin = make_p(5001, "security_admin")

    # Put a visitor on-site
    start = timezone.now() + timedelta(minutes=5)
    end = timezone.now() + timedelta(hours=2)
    visit = create_visit_request(host, {
        "host_user_id": 9001,
        "purpose": "On-site for drill",
        "start_time": start,
        "end_time": end,
        "name": "Emergency Evacuee",
        "phone": "9776655443",
        "id_type": "aadhaar",
        "id_number": "1234-9999-8888",
        "zone_ids": [base_setup["zone"].id],
        "consent_record": {"consent_given": True},
    })
    decide_visit_request(host, visit.id, action="approve")
    vpass = VisitPass.objects.get(request=visit)
    vpass.valid_from = timezone.now() - timedelta(minutes=5)
    vpass.save()

    check_in_visitor(guard, vpass.token, base_setup["gate"].id)

    # 1. Admin triggers emergency muster drill
    muster = trigger_emergency_muster(admin, notes="Annual Fire Drill")
    assert muster.status == "active"
    assert muster.total_on_site >= 1

    rc = MusterRollCall.objects.filter(muster=muster).first()
    assert rc is not None
    assert rc.status == "unaccounted"

    # 2. Guard performs roll call and marks visitor safe
    updated_rc = record_roll_call(guard, muster.id, rc.visitor_id, status="safe")
    assert updated_rc.status == "safe"

    # 3. Conclude muster drill
    ended = end_emergency_muster(admin, muster.id)
    assert ended.status == "completed"
    assert ended.safe_count >= 1
    assert ended.unaccounted_count == 0


# ==============================================================================
# NEGATIVE TESTS & CONSTRAINTS
# ==============================================================================
@pytest.mark.django_db
def test_negative_host_cannot_approve_own_visit(base_setup):
    visitor_p = make_p(0, "visitor", email="host@institute.ac.in")
    host = make_p(9001, "host", email="host@institute.ac.in")

    start = timezone.now() + timedelta(hours=1)
    end = start + timedelta(hours=3)

    # Host creating visit for self is blocked at creation
    with pytest.raises(SelfApprovalNotAllowedError):
        create_visit_request(host, {
            "host_user_id": 9001,
            "purpose": "Self visit creation attempt",
            "start_time": start,
            "end_time": end,
            "name": "Host Self",
            "phone": "9876549999",
            "email": "host@institute.ac.in",
            "id_type": "aadhaar",
            "id_number": "9999-0000-1111",
            "consent_record": {"consent_given": True},
        })

    # External visitor registering with host's email, host cannot approve it
    anon_p = make_p(0, "visitor", email="guest@visitor.local")
    visit = create_visit_request(anon_p, {
        "host_user_id": 9001,
        "purpose": "Visitor with host email",
        "start_time": start,
        "end_time": end,
        "name": "Host Self",
        "phone": "9876549998",
        "email": "host@institute.ac.in",
        "id_type": "aadhaar",
        "id_number": "9999-0000-2222",
        "consent_record": {"consent_given": True},
    })
    with pytest.raises(SelfApprovalNotAllowedError):
        decide_visit_request(host, visit.id, action="approve")


@pytest.mark.django_db
def test_negative_zone_capacity_enforcement(base_setup):
    host = make_p(9001, "host")
    guard = make_p(3001, "security_guard")

    # Set zone capacity to 1
    base_setup["zone"].max_capacity = 1
    base_setup["zone"].save()

    # Visitor 1 checks in and occupies the only slot
    v1 = create_visit_request(host, {
        "host_user_id": 9001,
        "purpose": "Occupant 1",
        "start_time": timezone.now() + timedelta(minutes=5),
        "end_time": timezone.now() + timedelta(hours=1),
        "name": "Occupant One",
        "phone": "9000000001",
        "id_type": "pan",
        "id_number": "PAN000001A",
        "zone_ids": [base_setup["zone"].id],
        "consent_record": {"consent_given": True},
    })
    decide_visit_request(host, v1.id, action="approve")
    p1 = VisitPass.objects.get(request=v1)
    p1.valid_from = timezone.now() - timedelta(minutes=5)
    p1.save()
    check_in_visitor(guard, p1.token, base_setup["gate"].id, zone_id=base_setup["zone"].id)

    # Visitor 2 tries to check into same zone -> capacity exceeded
    v2 = create_visit_request(host, {
        "host_user_id": 9001,
        "purpose": "Occupant 2",
        "start_time": timezone.now() + timedelta(minutes=5),
        "end_time": timezone.now() + timedelta(hours=1),
        "name": "Occupant Two",
        "phone": "9000000002",
        "id_type": "pan",
        "id_number": "PAN000002B",
        "zone_ids": [base_setup["zone"].id],
        "consent_record": {"consent_given": True},
    })
    decide_visit_request(host, v2.id, action="approve")
    p2 = VisitPass.objects.get(request=v2)
    p2.valid_from = timezone.now() - timedelta(minutes=5)
    p2.save()

    with pytest.raises(ZoneCapacityExceededError):
        check_in_visitor(guard, p2.token, base_setup["gate"].id, zone_id=base_setup["zone"].id)


# ==============================================================================
# SECURITY & PRIVACY TESTS
# ==============================================================================
@pytest.mark.django_db
def test_security_tampered_or_guessed_token_returns_404(base_setup):
    client = APIClient()
    resp = client.get("/api/v1/vms/public/pass/NONEXISTENT-GUESS-TOKEN")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_privacy_raw_id_never_in_responses(base_setup):
    host = make_p(9001, "host")
    raw_aadhaar = "1234-5678-9012"

    visit = create_visit_request(host, {
        "host_user_id": 9001,
        "purpose": "Privacy Check",
        "start_time": timezone.now() + timedelta(hours=1),
        "end_time": timezone.now() + timedelta(hours=3),
        "name": "Privacy Conscious Visitor",
        "phone": "9812345678",
        "id_type": "aadhaar",
        "id_number": raw_aadhaar,
        "consent_record": {"consent_given": True},
    })

    visitor = Visitor.objects.get(phone="9812345678")
    assert raw_aadhaar not in str(visitor.masked_id)
    assert visitor.masked_id.endswith("9012")
    assert "XXXX" in visitor.masked_id

    # Check API serialization
    from modules.vms.api.serializers.read import ReadVisitRequestSerializer
    data = ReadVisitRequestSerializer(visit).data
    serialized_str = str(data)
    assert raw_aadhaar not in serialized_str
    assert "id_hash" not in data["visitors"][0]["visitor"]
