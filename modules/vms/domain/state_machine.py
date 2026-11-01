"""VMS Pure Domain State Machine Transition Table."""
from dataclasses import dataclass
from modules.vms.domain.errors import ActorNotAllowedError, GuardFailedError, InvalidTransitionError

DRAFT, PENDING_HOST_APPROVAL = "draft", "pending_host_approval"
PENDING_SECOND_APPROVAL, PENDING_ADMIN_CONTINGENCY = "pending_second_approval", "pending_admin_contingency"
APPROVED, PASS_ISSUED, ON_SITE = "approved", "pass_issued", "on_site"
COMPLETED, REJECTED, CANCELLED, EXPIRED, OVERSTAY = "completed", "rejected", "cancelled", "expired", "overstay"

TERMINAL_STATES = frozenset([COMPLETED, REJECTED, CANCELLED, EXPIRED])
IN_FLIGHT_STATES = frozenset([PENDING_HOST_APPROVAL, PENDING_SECOND_APPROVAL, PENDING_ADMIN_CONTINGENCY, APPROVED, PASS_ISSUED, ON_SITE, OVERSTAY])
ALL_STATES = frozenset([DRAFT, PENDING_HOST_APPROVAL, PENDING_SECOND_APPROVAL, PENDING_ADMIN_CONTINGENCY, APPROVED, PASS_ISSUED, ON_SITE, COMPLETED, REJECTED, CANCELLED, EXPIRED, OVERSTAY])

VISITOR, HOST, DEPT_APPROVER = "visitor", "host", "dept_approver"
SECURITY_GUARD, RECEPTION, SECURITY_ADMIN = "security_guard", "reception", "security_admin"
SYSTEM, ADMIN, SUPER_ADMIN = "system", "admin", "super_admin"

STAFF_APPROVERS = frozenset([DEPT_APPROVER, SECURITY_ADMIN, ADMIN, SUPER_ADMIN])
GUARD_ROLES = frozenset([SECURITY_GUARD, RECEPTION, SECURITY_ADMIN, ADMIN, SUPER_ADMIN])


@dataclass(frozen=True)
class Transition:
    frm: str
    to: str
    action: str
    allowed_roles: frozenset[str]
    guard: str | None = None
    description: str = ""


TRANSITIONS = [
    Transition(DRAFT, PENDING_HOST_APPROVAL, "submit_request", frozenset([HOST, VISITOR, RECEPTION, ADMIN, SUPER_ADMIN]), "visitor_screened"),
    Transition(PENDING_HOST_APPROVAL, APPROVED, "host_approve", frozenset([HOST, DEPT_APPROVER, ADMIN, SUPER_ADMIN]), "host_not_visitor"),
    Transition(PENDING_HOST_APPROVAL, PENDING_SECOND_APPROVAL, "escalate_second_approval", frozenset([HOST, DEPT_APPROVER, SYSTEM, ADMIN, SUPER_ADMIN]), "requires_second_level"),
    Transition(PENDING_HOST_APPROVAL, PENDING_ADMIN_CONTINGENCY, "walkin_host_timeout", frozenset([SYSTEM, RECEPTION, SECURITY_ADMIN, ADMIN]), "walkin_sla_breached"),
    Transition(PENDING_HOST_APPROVAL, REJECTED, "host_reject", frozenset([HOST, DEPT_APPROVER, ADMIN, SUPER_ADMIN]), "has_rejection_reason"),
    Transition(PENDING_HOST_APPROVAL, CANCELLED, "cancel_request", frozenset([HOST, VISITOR, RECEPTION, ADMIN, SUPER_ADMIN])),
    Transition(PENDING_SECOND_APPROVAL, APPROVED, "second_level_approve", STAFF_APPROVERS, "approver_authorized"),
    Transition(PENDING_SECOND_APPROVAL, REJECTED, "second_level_reject", STAFF_APPROVERS, "has_rejection_reason"),
    Transition(PENDING_SECOND_APPROVAL, CANCELLED, "cancel_request", frozenset([HOST, VISITOR, ADMIN, SUPER_ADMIN])),
    Transition(PENDING_ADMIN_CONTINGENCY, APPROVED, "contingency_approve", STAFF_APPROVERS, "approver_authorized"),
    Transition(PENDING_ADMIN_CONTINGENCY, REJECTED, "contingency_reject", STAFF_APPROVERS, "has_rejection_reason"),
    Transition(PENDING_ADMIN_CONTINGENCY, CANCELLED, "cancel_request", frozenset([HOST, VISITOR, RECEPTION, ADMIN, SUPER_ADMIN])),
    Transition(APPROVED, PASS_ISSUED, "issue_pass", frozenset([SYSTEM, HOST, RECEPTION, SECURITY_GUARD, ADMIN, SUPER_ADMIN]), "pass_generated"),
    Transition(APPROVED, CANCELLED, "cancel_request", frozenset([HOST, VISITOR, RECEPTION, ADMIN, SUPER_ADMIN])),
    Transition(PASS_ISSUED, ON_SITE, "gate_check_in", GUARD_ROLES, "pass_valid_and_id_verified"),
    Transition(PASS_ISSUED, EXPIRED, "pass_expired", frozenset([SYSTEM, SECURITY_ADMIN, ADMIN, SUPER_ADMIN]), "validity_window_passed"),
    Transition(PASS_ISSUED, CANCELLED, "cancel_request", frozenset([HOST, VISITOR, RECEPTION, ADMIN, SUPER_ADMIN])),
    Transition(ON_SITE, COMPLETED, "gate_check_out", GUARD_ROLES, "items_verified"),
    Transition(ON_SITE, OVERSTAY, "flag_overstay", frozenset([SYSTEM, SECURITY_GUARD, SECURITY_ADMIN, ADMIN, SUPER_ADMIN]), "duration_exceeded"),
    Transition(OVERSTAY, COMPLETED, "late_check_out", GUARD_ROLES, "overstay_recorded"),
]

_INDEX = {(t.frm, t.to): t for t in TRANSITIONS}


def resolve(frm: str, to: str, actor: str | None = None) -> Transition:
    t = _INDEX.get((frm, to))
    if t is None:
        raise InvalidTransitionError(frm, to)
    if actor is not None and actor not in t.allowed_roles:
        raise ActorNotAllowedError(actor, frm, to)
    return t


def validate_guard(guard_name: str, context: dict) -> None:
    if guard_name == "has_rejection_reason" and not str(context.get("reason", "")).strip():
        raise GuardFailedError(guard_name, "Rejection justification is mandatory.")
    if guard_name == "requires_second_level" and not context.get("requires_second_approval", False):
        raise GuardFailedError(guard_name, "Visit does not qualify for second-level approval.")
    if guard_name == "host_not_visitor" and context.get("is_self_visit", False):
        raise GuardFailedError(guard_name, "Host cannot approve own visit.")
