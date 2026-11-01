"""VMS Pure Domain Business Rules."""
from datetime import datetime
from modules.vms.domain.errors import (
    BlacklistMatchError, PassWindowInvalidError, SelfApprovalNotAllowedError,
    VmsDomainError, ZoneCapacityExceededError,
)


def screen_blacklist(name: str, phone: str, id_hash: str, active_entries: list[dict]) -> None:
    norm_phone = phone.replace(" ", "").replace("-", "") if phone else ""
    for bl in active_entries:
        bl_phone = (bl.get("phone") or "").replace(" ", "").replace("-", "")
        if (norm_phone and bl_phone and norm_phone == bl_phone) or \
           (id_hash and bl.get("id_hash") and id_hash == bl.get("id_hash")) or \
           (name and bl.get("name") and name.strip().lower() == bl.get("name", "").strip().lower()):
            raise BlacklistMatchError(name, bl.get("reason", "Watchlist security flag"), severity=bl.get("severity", "block"))


def assert_host_not_visitor(host_user_id: int, visitor_user_id: int | None) -> None:
    if visitor_user_id is not None and host_user_id == visitor_user_id:
        raise SelfApprovalNotAllowedError(host_user_id)


def validate_visit_duration(duration_minutes: int, max_duration_hours: int) -> None:
    max_m = max_duration_hours * 60
    if duration_minutes > max_m:
        raise VmsDomainError(f"Duration ({duration_minutes}m) exceeds max ({max_m}m).", code="duration_limit_exceeded")


def validate_advance_window(visit_start: datetime, current_time: datetime, max_advance_days: int) -> None:
    if visit_start < current_time:
        raise VmsDomainError("Visit start time cannot be in the past.", code="start_in_past")
    if (visit_start - current_time).days > max_advance_days:
        raise VmsDomainError(f"Cannot book > {max_advance_days} days in advance.", code="advance_booking_exceeded")


def validate_pass_window(current_time: datetime, valid_from: datetime, valid_to: datetime) -> None:
    if current_time < valid_from:
        raise PassWindowInvalidError(f"Pass not yet valid. Begins at {valid_from.isoformat()}.")
    if current_time > valid_to:
        raise PassWindowInvalidError(f"Pass has expired. Expired at {valid_to.isoformat()}.")


def validate_zone_capacity(zone_name: str, current_occupancy: int, max_capacity: int, adding: int = 1) -> None:
    if current_occupancy + adding > max_capacity:
        raise ZoneCapacityExceededError(zone_name, max_capacity)


def validate_mandatory_registration(data: dict) -> None:
    for field in ["name", "phone", "id_type", "id_number", "purpose", "start_time", "end_time"]:
        if not data.get(field):
            raise VmsDomainError(f"Field '{field}' is mandatory for visit registration.", code="missing_field")


def is_overstay(current_time: datetime, expected_end: datetime, threshold_minutes: int = 15) -> bool:
    from datetime import timedelta
    return current_time > (expected_end + timedelta(minutes=threshold_minutes))


def check_duplicate_visit(active_visit_windows: list[tuple[datetime, datetime]], start_time: datetime, end_time: datetime) -> bool:
    return any(start_time < existing_end and end_time > existing_start for existing_start, existing_end in active_visit_windows)
