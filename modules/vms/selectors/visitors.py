"""Selectors for Visitor profiles."""
from __future__ import annotations

from typing import Any, Sequence

from django.db.models import QuerySet
from core.api.exceptions import NotFoundError
from modules.vms.models import Visitor


def get_visitor_summaries_by_ids(visitor_ids: Sequence[int]) -> dict[int, dict]:
    """Plural getter for contracts.py."""
    visitors = Visitor.objects.filter(id__in=visitor_ids)
    return {
        v.id: {
            "id": v.id,
            "name": v.name,
            "organisation": v.organisation,
            "masked_id": v.masked_id,
            "is_anonymized": v.is_anonymized,
        }
        for v in visitors
    }


def visible_visitors(principal: Any) -> QuerySet[Visitor]:
    """List of visitors visible to the principal."""
    if principal.has_any_permission("vms.report.view", "vms.audit.view", "vms.policy.manage", "vms.pass.scan"):
        return Visitor.objects.all().order_by("-created_at")

    # Host sees visitors who have visited them
    return Visitor.objects.filter(visits__request__host_user_id=principal.user_id).distinct().order_by("-created_at")


def get_visitor_for_principal(principal: Any, visitor_id: int) -> Visitor:
    try:
        return visible_visitors(principal).get(id=visitor_id)
    except Visitor.DoesNotExist:
        raise NotFoundError(f"Visitor #{visitor_id} not found.")
