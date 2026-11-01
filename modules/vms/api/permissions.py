"""Reusable permission checks for the Visitor Management System."""
from fusion_auth.permissions import HasPermission

# Visit requests & approvals
CanViewSelfVisits = HasPermission("vms.visit_request.view_self")
CanCreateVisit = HasPermission("vms.visit_request.create")
CanViewAllVisits = HasPermission("vms.visit_request.view")
CanApproveHostVisit = HasPermission("vms.visit_request.approve_host")
CanApproveSecondLevel = HasPermission("vms.visit_request.approve_second_level")
CanCancelVisit = HasPermission("vms.visit_request.cancel")
CanExtendVisit = HasPermission("vms.visit_request.extend")

# Passes & gate check-in/out
CanViewSelfPass = HasPermission("vms.pass.view_self")
CanScanPass = HasPermission("vms.pass.scan")
CanIssuePass = HasPermission("vms.pass.issue")
CanCheckInOutGate = HasPermission("vms.gate.check_in_out")
CanRegisterWalkin = HasPermission("vms.walkin.register")
CanOverrideGate = HasPermission("vms.override.gate")

# Blacklist & security
CanViewBlacklist = HasPermission("vms.blacklist.view")
CanManageBlacklist = HasPermission("vms.blacklist.manage")
CanReportIncident = HasPermission("vms.incident.report")

# Gates, zones & policies
CanViewZones = HasPermission("vms.zone.view")
CanManageZones = HasPermission("vms.zone.manage")
CanManageGates = HasPermission("vms.gate.manage")
CanManagePolicies = HasPermission("vms.policy.manage")

# Emergency muster
CanTriggerEmergency = HasPermission("vms.emergency.trigger")
CanPerformRollCall = HasPermission("vms.emergency.roll_call")

# Reports, audit & retention
CanViewReports = HasPermission("vms.report.view")
CanExportReports = HasPermission("vms.report.export")
CanViewAudit = HasPermission("vms.audit.view")
CanManageRetention = HasPermission("vms.retention.manage")
