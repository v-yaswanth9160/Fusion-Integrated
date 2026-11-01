"""What the server tells the shell about the Visitor Management System (VMS).

Nav items carry `required_permission` and the server filters before sending —
the client does zero filtering, so a link a role cannot use never reaches the
browser.
"""

MODULE = {
    "code": "vms",
    "label": "Visitor Management",
    "icon": "FaIdBadge",
    "base_path": "/vms",
    "nav_section": "Campus",
    "sort_order": 40,
    "status": "active",
}

NAV_ITEMS = [
    # -- Host (any faculty/staff) -----------------------------------------
    {
        "code": "vms.host.dashboard",
        "label": "My Visits",
        "icon": "FaIdBadge",
        "to": "/vms/host",
        "required_permission": "vms.visit_request.view_self",
        "sort_order": 10,
    },
    # -- Department Approver -----------------------------------------------
    {
        "code": "vms.approvals",
        "label": "Approval Queue",
        "icon": "FaClipboardCheck",
        "to": "/vms/approvals",
        "required_permission": "vms.visit_request.approve_second_level",
        "sort_order": 20,
    },
    # -- Security Guard / Gatekeeper ---------------------------------------
    {
        "code": "vms.guard",
        "label": "Guard Console",
        "icon": "FaShieldAlt",
        "to": "/vms/guard",
        "required_permission": "vms.pass.scan",
        "sort_order": 30,
    },
    # -- Reception Desk ----------------------------------------------------
    {
        "code": "vms.reception",
        "label": "Reception Desk",
        "icon": "FaConciergeBell",
        "to": "/vms/reception",
        "required_permission": "vms.walkin.register",
        "sort_order": 40,
    },
    # -- Security Admin Console --------------------------------------------
    {
        "code": "vms.admin",
        "label": "Security Admin",
        "icon": "FaUserShield",
        "to": "/vms/admin",
        "required_permission": "vms.policy.manage",
        "sort_order": 50,
    },
    # -- Emergency Muster Roll Call ----------------------------------------
    {
        "code": "vms.muster",
        "label": "Emergency Muster",
        "icon": "FaExclamationTriangle",
        "to": "/vms/muster",
        "required_permission": "vms.emergency.roll_call",
        "sort_order": 60,
    },
    # -- Operational Reports & Audit ---------------------------------------
    {
        "code": "vms.reports",
        "label": "Visitor Reports",
        "icon": "FaChartBar",
        "to": "/vms/reports",
        "required_permission": "vms.report.view",
        "sort_order": 70,
    },
]

PERMISSIONS = [
    # Visit requests & approvals
    ("vms.visit_request.view_self", "View one's own visit requests or hosted visits"),
    ("vms.visit_request.create", "Create or submit visit requests"),
    ("vms.visit_request.view", "View all visit requests within scope"),
    ("vms.visit_request.approve_host", "Approve or reject visits hosted by self"),
    ("vms.visit_request.approve_second_level", "Approve requests needing second-level approval"),
    ("vms.visit_request.cancel", "Cancel pending visit requests"),
    ("vms.visit_request.extend", "Request or approve visit duration extensions"),

    # Passes & gate check-in/out
    ("vms.pass.view_self", "View digital pass and QR code"),
    ("vms.pass.scan", "Scan and verify QR passes at gate"),
    ("vms.pass.issue", "Issue or print physical/digital visitor passes"),
    ("vms.gate.check_in_out", "Check in and check out visitors at gate"),
    ("vms.walkin.register", "Register walk-in visitors at gate/reception"),
    ("vms.override.gate", "Authorize manual gate override on verification failure"),

    # Blacklist & security
    ("vms.blacklist.view", "View blacklist and watchlist entries"),
    ("vms.blacklist.manage", "Add, edit or deactivate blacklist entries"),
    ("vms.incident.report", "Flag and report security incidents"),

    # Gates, zones & policies
    ("vms.zone.view", "View campus zones and current occupancy"),
    ("vms.zone.manage", "Configure campus zones, restricted flags and capacities"),
    ("vms.gate.manage", "Configure campus entry/exit gates"),
    ("vms.policy.manage", "Manage visit policies and system thresholds"),

    # Emergency muster
    ("vms.emergency.trigger", "Trigger emergency evacuation muster drill"),
    ("vms.emergency.roll_call", "Perform roll call and mark visitors safe/unaccounted"),

    # Reports, audit & retention
    ("vms.report.view", "View operational visitor logs and analytics"),
    ("vms.report.export", "Export visitor and audit data"),
    ("vms.audit.view", "View immutable audit logs"),
    ("vms.retention.manage", "Configure retention period and trigger anonymisation"),
]

SYSTEM_PERMISSIONS = [
    "vms.pass.auto_expire",
    "vms.visit.auto_overstay",
    "vms.retention.auto_anonymize",
    "vms.notification.auto_send",
]

_VISITOR = [
    "vms.visit_request.view_self",
    "vms.visit_request.create",
    "vms.visit_request.cancel",
    "vms.pass.view_self",
]

_HOST = [
    "vms.visit_request.view_self",
    "vms.visit_request.create",
    "vms.visit_request.approve_host",
    "vms.visit_request.cancel",
    "vms.visit_request.extend",
    "vms.pass.view_self",
]

_DEPT_APPROVER = [
    *_HOST,
    "vms.visit_request.view",
    "vms.visit_request.approve_second_level",
]

_SECURITY_GUARD = [
    "vms.pass.scan",
    "vms.pass.issue",
    "vms.gate.check_in_out",
    "vms.incident.report",
    "vms.emergency.roll_call",
    "vms.zone.view",
]

_RECEPTION = [
    "vms.walkin.register",
    "vms.pass.issue",
    "vms.gate.check_in_out",
    "vms.visit_request.view",
    "vms.zone.view",
]

_SECURITY_ADMIN = [
    "vms.blacklist.view",
    "vms.blacklist.manage",
    "vms.zone.view",
    "vms.zone.manage",
    "vms.gate.manage",
    "vms.policy.manage",
    "vms.emergency.trigger",
    "vms.emergency.roll_call",
    "vms.override.gate",
    "vms.report.view",
    "vms.report.export",
    "vms.audit.view",
    "vms.visit_request.view",
    "vms.visit_request.approve_second_level",
    "vms.incident.report",
    "vms.pass.scan",
]

_SUPER_ADMIN = [
    *[code for code, _ in PERMISSIONS],
]

_AUDITOR = [
    "vms.report.view",
    "vms.report.export",
    "vms.audit.view",
    "vms.zone.view",
    "vms.blacklist.view",
]

ROLE_GRANTS = {
    "visitor": _VISITOR,
    "host": _HOST,
    "faculty": _HOST,
    "staff": _HOST,
    "dept_approver": _DEPT_APPROVER,
    "Dean Academic": _DEPT_APPROVER,
    "security_guard": _SECURITY_GUARD,
    "reception": _RECEPTION,
    "security_admin": _SECURITY_ADMIN,
    "super_admin": _SUPER_ADMIN,
    "admin": _SUPER_ADMIN,
    "auditor": _AUDITOR,
}
