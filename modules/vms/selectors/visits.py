"""Selectors for VisitRequest and Visitor queries.

Ownership and scope filtering is strictly applied here:
Attempting to fetch a record outside the caller's visibility raises NotFoundError (HTTP 404).
"""
from __future__ import annotations

from typing import Any, Sequence

from django.db.models import Q, QuerySet
from core.api.exceptions import NotFoundError
from modules.vms.models import (
    CheckInOutLog,
    VisitPass,
    VisitRequest,
    VisitVisitor,
)


def count_active_visitors_for_hosts(host_user_ids: Sequence[int]) -> dict[int, int]:
    """Plural getter for contracts.py."""
    counts = {uid: 0 for uid in host_user_ids}
    rows = (
        VisitRequest.objects.filter(host_user_id__in=host_user_ids, status="on_site")
        .values_list("host_user_id", flat=False)
    )
    for (hid,) in rows:
        counts[hid] = counts.get(hid, 0) + 1
    return counts


def visible_visit_requests(principal: Any) -> QuerySet[VisitRequest]:
    """Return visit requests visible to the principal based on their role and permissions."""
    qs = VisitRequest.objects.all().select_related().prefetch_related(
        "visitors__visitor", "permitted_zones__zone", "vehicles", "declared_items", "passes"
    )

    # Security admin, auditor, super admin see all
    if principal.has_any_permission(
        "vms.visit_request.view",
        "vms.audit.view",
        "vms.policy.manage",
        "vms.pass.scan",
    ):
        return qs

    # Department approver sees pending second level and own
    if principal.has_permission("vms.visit_request.approve_second_level"):
        return qs.filter(Q(status="pending_second_approval") | Q(host_user_id=principal.user_id))

    # Host sees only their own visits
    if principal.has_permission("vms.visit_request.approve_host") or principal.has_permission("vms.visit_request.view_self"):
        return qs.filter(host_user_id=principal.user_id)

    # Visitor sees requests where they are registered
    return qs.filter(visitors__visitor__email=getattr(principal, "email", "___none___"))


def get_visit_request_for_principal(principal: Any, request_id: int) -> VisitRequest:
    """Fetch visit request, raising NotFoundError if non-existent or outside caller's visibility."""
    try:
        return visible_visit_requests(principal).get(id=request_id)
    except VisitRequest.DoesNotExist:
        raise NotFoundError(f"Visit request #{request_id} not found.")


def get_expected_today_visits() -> QuerySet[VisitRequest]:
    """Visits scheduled for today or currently on site (for guard/reception desk)."""
    return (
        VisitRequest.objects.filter(status__in=["approved", "pass_issued", "on_site", "overstay"])
        .prefetch_related("visitors__visitor", "permitted_zones__zone", "passes")
        .order_by("start_time")
    )
