"""Selectors for operational logs, analytics, and audit trail."""
from __future__ import annotations

from datetime import datetime
from typing import Any, Mapping

from django.db.models import Count, QuerySet
from modules.vms.models import (
    AuditLogEntry,
    CheckInOutLog,
    Incident,
    VisitRequest,
)


def get_daily_logs(target_date: datetime.date | None = None) -> QuerySet[CheckInOutLog]:
    qs = CheckInOutLog.objects.select_related("visitor", "request", "gate", "zone").order_by("-timestamp")
    if target_date:
        qs = qs.filter(timestamp__date=target_date)
    return qs


def get_overstay_incidents() -> QuerySet[Incident]:
    return Incident.objects.filter(category="overstay").select_related("request", "visitor", "gate").order_by("-created_at")


def get_host_visit_summaries() -> list[Mapping[str, Any]]:
    rows = (
        VisitRequest.objects.values("host_user_id")
        .annotate(
            total_visits=Count("id"),
            active_now=Count("id", filter=CheckInOutLog.objects.filter(action="check_in").query.where if False else None),
        )
        .order_by("-total_visits")
    )
    return list(rows)


def get_audit_trail(entity_type: str | None = None) -> QuerySet[AuditLogEntry]:
    qs = AuditLogEntry.objects.all().order_by("-timestamp")
    if entity_type:
        qs = qs.filter(entity_type=entity_type)
    return qs
