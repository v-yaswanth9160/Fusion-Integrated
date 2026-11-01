"""Table-driven RBAC tests for VMS.

Verifies role-to-permission mappings, deny-by-default semantics, and isolation
across all VMS roles.
"""
import pytest

from conftest import make_principal
from modules.vms.api.permissions import (
    CanApproveHostVisit,
    CanApproveSecondLevel,
    CanCheckInOutGate,
    CanCreateVisit,
    CanExportReports,
    CanManageBlacklist,
    CanManagePolicies,
    CanManageZones,
    CanOverrideGate,
    CanPerformRollCall,
    CanRegisterWalkin,
    CanReportIncident,
    CanScanPass,
    CanTriggerEmergency,
    CanViewAudit,
    CanViewBlacklist,
    CanViewReports,
    CanViewSelfPass,
    CanViewSelfVisits,
)
from modules.vms.registry import PERMISSIONS, ROLE_GRANTS, SYSTEM_PERMISSIONS


class DummyView:
    pass


def _check(permission_cls, principal) -> bool:
    class Req:
        pass

    req = Req()
    req.principal = principal
    return permission_cls().has_permission(req, DummyView())


# Matrix of key roles and expected access to critical capabilities
ROLE_CAPABILITY_MATRIX = [
    # (role, can_create_visit, can_approve_host, can_approve_2nd, can_scan_pass, can_walkin, can_manage_bl, can_manage_policy, can_audit)
    ("visitor", True, False, False, False, False, False, False, False),
    ("host", True, True, False, False, False, False, False, False),
    ("dept_approver", True, True, True, False, False, False, False, False),
    ("security_guard", False, False, False, True, False, False, False, False),
    ("reception", False, False, False, False, True, False, False, False),
    ("security_admin", False, False, True, True, False, True, True, True),
    ("auditor", False, False, False, False, False, False, False, True),
]


@pytest.mark.parametrize(
    "role,can_create,can_app_host,can_app_2nd,can_scan,can_walkin,can_bl,can_policy,can_audit",
    ROLE_CAPABILITY_MATRIX,
)
def test_role_capability_matrix(
    role,
    can_create,
    can_app_host,
    can_app_2nd,
    can_scan,
    can_walkin,
    can_bl,
    can_policy,
    can_audit,
):
    perms = ROLE_GRANTS.get(role, [])
    p = make_principal(roles=(role,), active_role=role, permissions=perms, modules=("vms",))

    assert _check(CanCreateVisit, p) is can_create, f"{role} create visit mismatch"
    assert _check(CanApproveHostVisit, p) is can_app_host, f"{role} approve host mismatch"
    assert _check(CanApproveSecondLevel, p) is can_app_2nd, f"{role} approve 2nd mismatch"
    assert _check(CanScanPass, p) is can_scan, f"{role} scan pass mismatch"
    assert _check(CanRegisterWalkin, p) is can_walkin, f"{role} walkin register mismatch"
    assert _check(CanManageBlacklist, p) is can_bl, f"{role} blacklist manage mismatch"
    assert _check(CanManagePolicies, p) is can_policy, f"{role} policy manage mismatch"
    assert _check(CanViewAudit, p) is can_audit, f"{role} audit view mismatch"


def test_deny_by_default_for_unauthenticated_or_empty_principal():
    class Req:
        principal = None

    for checker in [
        CanViewSelfVisits,
        CanCreateVisit,
        CanApproveHostVisit,
        CanScanPass,
        CanManageBlacklist,
    ]:
        assert checker().has_permission(Req(), DummyView()) is False


def test_system_permissions_are_never_granted_to_roles():
    """No human role should ever hold an automated system job permission."""
    system_set = set(SYSTEM_PERMISSIONS)
    for role, granted in ROLE_GRANTS.items():
        overlap = set(granted) & system_set
        assert not overlap, f"Role {role} was granted system permissions: {overlap}"


def test_every_granted_permission_is_declared():
    """No role may hold a permission that is not listed in PERMISSIONS."""
    declared = {code for code, _ in PERMISSIONS}
    for role, granted in ROLE_GRANTS.items():
        unknown = set(granted) - declared
        assert not unknown, f"Role {role} has undeclared permissions: {unknown}"


def test_security_guard_cannot_approve_or_modify_blacklist():
    """Security guard must verify passes, but must never approve requests or edit blacklist."""
    guard_perms = ROLE_GRANTS["security_guard"]
    guard = make_principal(roles=("security_guard",), permissions=guard_perms, modules=("vms",))

    assert _check(CanApproveHostVisit, guard) is False
    assert _check(CanApproveSecondLevel, guard) is False
    assert _check(CanManageBlacklist, guard) is False
    assert _check(CanManagePolicies, guard) is False


def test_auditor_is_strictly_read_only():
    """Auditor can view logs and reports, but has zero write/approval/pass scan permissions."""
    auditor_perms = ROLE_GRANTS["auditor"]
    auditor = make_principal(roles=("auditor",), permissions=auditor_perms, modules=("vms",))

    assert _check(CanViewAudit, auditor) is True
    assert _check(CanViewReports, auditor) is True
    assert _check(CanExportReports, auditor) is True

    # Denials
    assert _check(CanCreateVisit, auditor) is False
    assert _check(CanApproveHostVisit, auditor) is False
    assert _check(CanApproveSecondLevel, auditor) is False
    assert _check(CanScanPass, auditor) is False
    assert _check(CanRegisterWalkin, auditor) is False
    assert _check(CanManageBlacklist, auditor) is False
    assert _check(CanManagePolicies, auditor) is False
