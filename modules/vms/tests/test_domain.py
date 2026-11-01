"""Fast, pure-Python domain tests for the VMS state machine and business rules.

Executes in milliseconds with zero database access.
"""
from datetime import datetime, timedelta, timezone
import pytest

from modules.vms.domain import business_rules as br
from modules.vms.domain import state_machine as sm
from modules.vms.domain.errors import (
    ActorNotAllowedError,
    BlacklistMatchError,
    InvalidTransitionError,
    PassWindowInvalidError,
    SelfApprovalNotAllowedError,
    VmsDomainError,
    ZoneCapacityExceededError,
)

ALL_STATES = sm.ALL_STATES


def test_transition_table_is_exhaustive():
    """Verify that every legal transition exists in the TRANSITIONS table."""
    declared = {(t.frm, t.to) for t in sm.TRANSITIONS}
    for frm in ALL_STATES:
        for to in ALL_STATES:
            assert sm.is_legal(frm, to) is ((frm, to) in declared)


def test_terminal_states_have_no_outgoing_transitions():
    """Terminal states (completed, rejected, cancelled, expired) cannot transition to any other state."""
    for s in sm.TERMINAL_STATES:
        assert sm.allowed_targets(s) == [], f"Terminal state '{s}' must have zero exits."


def test_illegal_transition_raises_typed_error():
    """Attempting an invalid jump (e.g. DRAFT to COMPLETED) must raise InvalidTransitionError."""
    with pytest.raises(InvalidTransitionError) as exc_info:
        sm.resolve(sm.DRAFT, sm.COMPLETED)
    assert exc_info.value.frm == sm.DRAFT
    assert exc_info.value.to == sm.COMPLETED


def test_unauthorized_actor_raises_actor_not_allowed():
    """A Visitor cannot approve a visit or check in at the gate."""
    with pytest.raises(ActorNotAllowedError):
        sm.resolve(sm.PENDING_HOST_APPROVAL, sm.APPROVED, actor=sm.VISITOR)

    with pytest.raises(ActorNotAllowedError):
        sm.resolve(sm.PASS_ISSUED, sm.ON_SITE, actor=sm.VISITOR)


def test_host_approval_transitions():
    """Host can approve standard visit or escalate to department approver."""
    t1 = sm.resolve(sm.PENDING_HOST_APPROVAL, sm.APPROVED, actor=sm.HOST)
    assert "no_second_approval_required" in t1.guards

    t2 = sm.resolve(sm.PENDING_HOST_APPROVAL, sm.PENDING_SECOND_APPROVAL, actor=sm.HOST)
    assert "requires_second_approval" in t2.guards


def test_department_approver_and_admin_transitions():
    """Department approver and Admin can approve second level requests."""
    t = sm.resolve(sm.PENDING_SECOND_APPROVAL, sm.APPROVED, actor=sm.DEPT_APPROVER)
    assert "second_approver_authorized" in t.guards

    t_admin = sm.resolve(sm.PENDING_SECOND_APPROVAL, sm.APPROVED, actor=sm.SECURITY_ADMIN)
    assert t_admin is not None


def test_guard_gate_transitions():
    """Security Guard can check in and check out visitors."""
    t_in = sm.resolve(sm.PASS_ISSUED, sm.ON_SITE, actor=sm.SECURITY_GUARD)
    assert "pass_valid_window" in t_in.guards
    assert "not_blacklisted" in t_in.guards
    assert "zone_capacity_available" in t_in.guards

    t_out = sm.resolve(sm.ON_SITE, sm.COMPLETED, actor=sm.SECURITY_GUARD)
    assert "items_verified" in t_out.guards


def test_overstay_and_rejection_transitions():
    """System flags overstay, Guard checks out late; Approver rejects with reason."""
    t_overstay = sm.resolve(sm.ON_SITE, sm.OVERSTAY, actor=sm.SYSTEM)
    assert "duration_exceeded" in t_overstay.guards

    t_late_out = sm.resolve(sm.OVERSTAY, sm.COMPLETED, actor=sm.SECURITY_GUARD)
    assert "overstay_acknowledged" in t_late_out.guards

    t_rej = sm.resolve(sm.PENDING_HOST_APPROVAL, sm.REJECTED, actor=sm.HOST)
    assert "has_rejection_reason" in t_rej.guards


# ---- Business Rules Pure-Python Tests ----

def test_br037_mandatory_registration_validation():
    valid = {
        "name": "Jane Doe",
        "phone": "9876543210",
        "id_type": "passport",
        "id_number": "P1234567",
        "purpose": "Guest Lecture",
        "start_time": "2026-11-02T10:00:00Z",
        "end_time": "2026-11-02T12:00:00Z",
    }
    br.validate_mandatory_registration(valid)

    invalid = valid.copy()
    invalid.pop("phone")
    with pytest.raises(VmsDomainError) as exc:
        br.validate_mandatory_registration(invalid)
    assert "phone" in str(exc.value)


def test_br038_duplicate_visit_check():
    t1 = datetime(2026, 11, 2, 10, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)
    windows = [(t1, t2)]

    # Overlapping window
    assert br.check_duplicate_visit(windows, t1 + timedelta(minutes=30), t2 + timedelta(minutes=30)) is True

    # Completely disjoint window
    t3 = datetime(2026, 11, 2, 14, 0, tzinfo=timezone.utc)
    t4 = datetime(2026, 11, 2, 16, 0, tzinfo=timezone.utc)
    assert br.check_duplicate_visit(windows, t3, t4) is False


def test_br051_blacklist_screening():
    bl_records = [
        {"name": "Bad Actor", "phone": "9999999999", "id_hash": "bad_hash_123", "reason": "Trespassing", "severity": "block", "is_active": True},
        {"name": "Ex Watchlist", "phone": "8888888888", "id_hash": "ex_hash", "reason": "Old", "is_active": False},
    ]

    # Clean person passes
    br.screen_blacklist("Good Citizen", "9111111111", "good_hash", bl_records)

    # Inactive blacklist entry does not block
    br.screen_blacklist("Ex Watchlist", "8888888888", "ex_hash", bl_records)

    # Blacklisted phone blocks
    with pytest.raises(BlacklistMatchError) as exc1:
        br.screen_blacklist("Random Name", "9999999999", "random_hash", bl_records)
    assert "Trespassing" in exc1.value.reason

    # Blacklisted ID hash blocks
    with pytest.raises(BlacklistMatchError) as exc2:
        br.screen_blacklist("Different Name", "7777777777", "bad_hash_123", bl_records)
    assert "Trespassing" in exc2.value.reason


def test_br052_host_cannot_approve_own_visit():
    with pytest.raises(SelfApprovalNotAllowedError):
        br.assert_host_not_visitor(host_user_id=101, visitor_user_id=101)

    # Different users allowed
    br.assert_host_not_visitor(host_user_id=101, visitor_user_id=202)


def test_br193_visit_duration_limit():
    # 2 hours under 8-hour cap passes
    br.validate_visit_duration(duration_minutes=120, max_duration_hours=8)

    # 10 hours exceeds 8-hour cap
    with pytest.raises(VmsDomainError):
        br.validate_visit_duration(duration_minutes=600, max_duration_hours=8)


def test_br190_pass_window_validation():
    now = datetime(2026, 11, 2, 10, 30, tzinfo=timezone.utc)
    valid_from = datetime(2026, 11, 2, 10, 0, tzinfo=timezone.utc)
    valid_to = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)

    # In-window passes
    br.validate_pass_window(now, valid_from, valid_to)

    # Too early
    with pytest.raises(PassWindowInvalidError):
        br.validate_pass_window(now - timedelta(hours=1), valid_from, valid_to)

    # Too late
    with pytest.raises(PassWindowInvalidError):
        br.validate_pass_window(now + timedelta(hours=3), valid_from, valid_to)


def test_zone_capacity_validation():
    # 10 out of 50 capacity is allowed
    br.validate_zone_capacity("Server Room", current_occupancy=10, max_capacity=50)

    # Unlimited capacity (max_capacity=0) is always allowed
    br.validate_zone_capacity("Open Campus", current_occupancy=500, max_capacity=0)

    # Reaching capacity raises ZoneCapacityExceededError
    with pytest.raises(ZoneCapacityExceededError):
        br.validate_zone_capacity("Server Room", current_occupancy=50, max_capacity=50)


def test_overstay_detection_math():
    now = datetime(2026, 11, 2, 12, 20, tzinfo=timezone.utc)
    expected_end = datetime(2026, 11, 2, 12, 0, tzinfo=timezone.utc)

    # Past 15 min threshold -> overstay
    assert br.is_overstay(now, expected_end, threshold_minutes=15) is True

    # Within 15 min grace period -> not overstay
    now_grace = datetime(2026, 11, 2, 12, 10, tzinfo=timezone.utc)
    assert br.is_overstay(now_grace, expected_end, threshold_minutes=15) is False
