"""URL routes for the Visitor Management System API."""
from django.urls import path

from modules.vms.api.views import (
    blacklist,
    gate,
    muster,
    public,
    reports,
    requests,
    zones,
)

urlpatterns = [
    # Public (unauthenticated)
    path("public/register", public.PublicRegisterView.as_view(), name="vms-public-register"),
    path("public/pass/<str:token>", public.PublicPassView.as_view(), name="vms-public-pass"),
    path("public/cancel/<str:token>", public.PublicCancelView.as_view(), name="vms-public-cancel"),

    # Visit Requests & Approvals
    path("requests", requests.VisitRequestListCreateView.as_view(), name="vms-requests-list-create"),
    path("requests/<int:pk>", requests.VisitRequestDetailView.as_view(), name="vms-requests-detail"),
    path("requests/<int:pk>/decide", requests.VisitRequestDecideView.as_view(), name="vms-requests-decide"),
    path("requests/<int:pk>/cancel", requests.VisitRequestCancelView.as_view(), name="vms-requests-cancel"),
    path("requests/<int:pk>/extend", requests.VisitRequestExtendView.as_view(), name="vms-requests-extend"),

    # Gate Operations & QR Verification
    path("gate/verify", gate.GateVerifyPassView.as_view(), name="vms-gate-verify"),
    path("gate/check-in", gate.GateCheckInView.as_view(), name="vms-gate-check-in"),
    path("gate/check-out", gate.GateCheckOutView.as_view(), name="vms-gate-check-out"),
    path("gate/walk-in", gate.GateWalkInView.as_view(), name="vms-gate-walkin"),
    path("gate/expected-today", gate.GateExpectedTodayView.as_view(), name="vms-gate-expected-today"),

    # Blacklist & Watchlist
    path("blacklist", blacklist.BlacklistListCreateView.as_view(), name="vms-blacklist-list-create"),
    path("blacklist/<int:pk>/toggle", blacklist.BlacklistToggleActiveView.as_view(), name="vms-blacklist-toggle"),

    # Gates, Zones & Policies
    path("gates", zones.GateListCreateView.as_view(), name="vms-gates"),
    path("zones", zones.ZoneListCreateView.as_view(), name="vms-zones"),
    path("policy", zones.VisitPolicyView.as_view(), name="vms-policy"),

    # Emergency Muster
    path("muster/active", muster.EmergencyMusterActiveView.as_view(), name="vms-muster-active"),
    path("muster/trigger", muster.EmergencyMusterTriggerView.as_view(), name="vms-muster-trigger"),
    path("muster/<int:muster_id>/roll-call/<int:visitor_id>", muster.EmergencyMusterRollCallView.as_view(), name="vms-muster-roll-call"),
    path("muster/<int:muster_id>/end", muster.EmergencyMusterEndView.as_view(), name="vms-muster-end"),

    # Reports & Audit
    path("reports/daily", reports.DailyReportView.as_view(), name="vms-reports-daily"),
    path("reports/overstays", reports.OverstayReportView.as_view(), name="vms-reports-overstays"),
    path("reports/hosts", reports.HostSummaryReportView.as_view(), name="vms-reports-hosts"),
    path("reports/export", reports.ExportReportView.as_view(), name="vms-reports-export"),
    path("audit", reports.AuditTrailView.as_view(), name="vms-audit"),
]
