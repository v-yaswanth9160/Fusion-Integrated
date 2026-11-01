"""Selectors for passes and gate verification."""
from __future__ import annotations

from core.api.exceptions import NotFoundError
from modules.vms.models import VisitPass


def get_pass_by_token(token: str) -> VisitPass:
    """Lookup pass by unguessable token."""
    try:
        return VisitPass.objects.select_related("visitor", "request").prefetch_related("request__permitted_zones__zone").get(token=token.strip())
    except VisitPass.DoesNotExist:
        raise NotFoundError("Invalid or non-existent pass token.")
