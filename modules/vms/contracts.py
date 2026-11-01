"""Cross-module public contract for VMS.

Per ADR-0013 and ops/checks/contracts_are_plural.py, this is the ONLY entry
point other modules may import. Every getter takes a sequence of IDs to
guarantee batched lookups without N+1 queries.
"""
from __future__ import annotations

from typing import Sequence


def get_active_visitor_counts(host_user_ids: Sequence[int]) -> dict[int, int]:
    """Return count of currently checked-in visitors for each host user ID."""
    from modules.vms.selectors.visits import count_active_visitors_for_hosts

    return count_active_visitors_for_hosts(host_user_ids)


def get_visitor_summaries(visitor_ids: Sequence[int]) -> dict[int, dict]:
    """Return masked visitor profiles for a sequence of visitor IDs."""
    from modules.vms.selectors.visitors import get_visitor_summaries_by_ids

    return get_visitor_summaries_by_ids(visitor_ids)
