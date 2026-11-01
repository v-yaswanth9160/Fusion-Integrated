"""Visit lifecycle services (Workflows A to G).

All database writes, mutations, atomic transactions, state transitions,
audit rows, and notifications go through this layer.
"""
from __future__ import annotations

import hashlib
from datetime import datetime, timedelta
from typing import Any, Mapping, Sequence
import uuid

from django.db import transaction
from django.utils import timezone

from modules.vms.domain import business_rules as br
from modules.vms.domain import state_machine as sm
from modules.vms.domain.errors import (
    BlacklistMatchError,
    GuardFailedError,
    PassAlreadyUsedError,
    SelfApprovalNotAllowedError,
    VmsDomainError,
)
from modules.vms.models import (
    BlacklistEntry,
    CheckInOutLog,
    DeclaredItem,
    Gate,
    Incident,
    Vehicle,
    Visitor,
    VisitPass,
    VisitPolicy,
    VisitRequest,
    VisitVisitor,
    VisitZone,
    Zone,
)
from modules.vms.services.audit import log_audit
from modules.vms.services.notifications import queue_notification


def get_active_policy() -> VisitPolicy:
    """Retrieve the latest active visit policy or create default if none exists."""
    policy = VisitPolicy.objects.filter(is_active=True).order_by("-version").first()
    if not policy:
        policy = VisitPolicy.objects.create(version=1, is_active=True)
    return policy


def hash_id(id_number: str) -> str:
    """Compute deterministic SHA-256 hash of normalized ID number."""
    normalized = id_number.strip().upper().replace(" ", "").replace("-", "")
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def mask_id(id_number: str) -> str:
    """Mask government ID number, showing only the last 4 characters."""
    clean = id_number.strip()
    if len(clean) <= 4:
        return "****"
    return "X" * (len(clean) - 4) + clean[-4:]


def create_visit_request(
    actor_principal: Any,
    data: Mapping[str, Any],
) -> VisitRequest:
    """Pre-register a standard or group visit (Workflow A & G)."""
    policy = get_active_policy()
    now = timezone.now()

    # Mandatory field validation (BR-037)
    br.validate_mandatory_registration(data)

    start_time = data["start_time"]
    end_time = data["end_time"]
    if isinstance(start_time, str):
        start_time = datetime.fromisoformat(start_time)
    if isinstance(end_time, str):
        end_time = datetime.fromisoformat(end_time)
    if timezone.is_naive(start_time):
        start_time = timezone.make_aware(start_time)
    if timezone.is_naive(end_time):
        end_time = timezone.make_aware(end_time)

    duration_minutes = int((end_time - start_time).total_seconds() // 60)
    br.validate_visit_duration(duration_minutes, policy.max_visit_duration_hours)
    br.validate_advance_window(start_time, now, policy.advance_booking_limit_days)

    host_user_id = int(data.get("host_user_id", actor_principal.user_id))

    # Host daily visitor cap check
    today_start = start_time.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)
    current_host_visits = VisitRequest.objects.filter(
        host_user_id=host_user_id,
        start_time__gte=today_start,
        start_time__lt=today_end,
    ).exclude(status__in=sm.TERMINAL_STATES).count()

    if current_host_visits >= policy.daily_host_visitor_cap:
        raise VmsDomainError(
            f"Host {host_user_id} has reached their daily visitor cap of {policy.daily_host_visitor_cap}.",
            code="host_cap_exceeded",
        )

    # Visitor profile and blacklist screening (BR-051, BR-112)
    id_number = str(data["id_number"])
    id_h = hash_id(id_number)
    masked = mask_id(id_number)
    phone = str(data["phone"]).strip()
    name = str(data["name"]).strip()

    # Screen against blacklist
    active_bl = list(BlacklistEntry.objects.filter(is_active=True).values())
    try:
        br.screen_blacklist(name, phone, id_h, active_bl)
    except BlacklistMatchError as exc:
        # Log incident and audit row
        Incident.objects.create(
            severity="critical" if exc.severity == "block" else "high",
            category="blacklist_attempt",
            description=f"Attempted registration of blacklisted visitor: {name} (Reason: {exc.reason})",
            reported_by_user_id=actor_principal.user_id,
        )
        log_audit(
            who_user_id=actor_principal.user_id,
            who_label=str(actor_principal),
            action="BLACKLIST_SCREENING_FAILED",
            entity_type="Visitor",
            entity_id=0,
            reason=exc.reason,
        )
        raise

    # Host self-approval restriction
    visitor_user_id = data.get("visitor_user_id")
    if visitor_user_id is not None:
        br.assert_host_not_visitor(host_user_id, int(visitor_user_id))
    actor_email = getattr(actor_principal, "email", "").strip()
    if actor_email and data.get("email") and actor_email.lower() == str(data.get("email")).strip().lower():
        br.assert_host_not_visitor(host_user_id, actor_principal.user_id)

    # Check duplicate visits (BR-038)
    existing_visits = VisitVisitor.objects.filter(
        visitor__id_hash=id_h,
        request__status__in=sm.IN_FLIGHT_STATES,
    ).values_list("request__start_time", "request__end_time")
    if br.check_duplicate_visit(list(existing_visits), start_time, end_time):
        raise VmsDomainError(
            f"A visit is already registered for {name} during the requested time window.",
            code="duplicate_visit",
        )

    with transaction.atomic():
        # Create Visitor
        visitor, _ = Visitor.objects.update_or_create(
            id_hash=id_h,
            defaults={
                "name": name,
                "phone": phone,
                "email": str(data.get("email", "")).strip(),
                "organisation": str(data.get("organisation", "")).strip(),
                "photo_url": str(data.get("photo_url", "")).strip(),
                "id_type": str(data["id_type"]),
                "masked_id": masked,
                "consent_given": bool(data.get("consent_given", True)),
                "consent_version": str(data.get("consent_version", "v1.0")),
                "consent_timestamp": now,
            },
        )

        # Determine second-level approval requirements (restricted zone or group size)
        zone_ids = data.get("zone_ids", [])
        has_restricted_zone = Zone.objects.filter(id__in=zone_ids, is_restricted=True).exists()
        companions = data.get("companions", [])
        is_large_group = len(companions) >= policy.require_second_approval_for_groups_above
        requires_second_level = has_restricted_zone or is_large_group

        # Create VisitRequest
        visit_type = data.get("visit_type", "group" if companions else "standard")
        req = VisitRequest.objects.create(
            host_user_id=host_user_id,
            purpose=str(data["purpose"]),
            visit_type=visit_type,
            start_time=start_time,
            end_time=end_time,
            expected_duration_minutes=duration_minutes,
            status=sm.PENDING_HOST_APPROVAL,
            requires_second_approval=requires_second_level,
        )

        # Attach primary visitor
        VisitVisitor.objects.create(request=req, visitor=visitor, is_primary=True, status="pending")

        # Attach companions (Workflow G)
        for comp_data in companions:
            comp_id_h = hash_id(str(comp_data["id_number"]))
            comp_visitor, _ = Visitor.objects.update_or_create(
                id_hash=comp_id_h,
                defaults={
                    "name": str(comp_data["name"]).strip(),
                    "phone": str(comp_data.get("phone", "")).strip(),
                    "email": str(comp_data.get("email", "")).strip(),
                    "organisation": str(comp_data.get("organisation", visitor.organisation)).strip(),
                    "id_type": str(comp_data["id_type"]),
                    "masked_id": mask_id(str(comp_data["id_number"])),
                    "consent_given": True,
                    "consent_timestamp": now,
                },
            )
            VisitVisitor.objects.create(request=req, visitor=comp_visitor, is_primary=False, status="pending")

        # Permitted zones
        for zid in zone_ids:
            zone = Zone.objects.filter(id=zid).first()
            if zone:
                VisitZone.objects.create(request=req, zone=zone)

        # Optional vehicle
        if vehicle_data := data.get("vehicle"):
            Vehicle.objects.create(
                request=req,
                vehicle_type=vehicle_data.get("vehicle_type", "four_wheeler"),
                registration_number=vehicle_data["registration_number"].strip().upper(),
                driver_name=vehicle_data.get("driver_name", ""),
                driver_contact=vehicle_data.get("driver_contact", ""),
                parking_bay=vehicle_data.get("parking_bay", ""),
            )

        # Optional declared items
        for item in data.get("declared_items", []):
            DeclaredItem.objects.create(
                request=req,
                item_name=item["item_name"],
                serial_number=item.get("serial_number", ""),
                category=item.get("category", "other"),
            )

        # Audit & Notification
        log_audit(
            who_user_id=actor_principal.user_id,
            who_label=str(actor_principal),
            action="CREATE_VISIT_REQUEST",
            entity_type="VisitRequest",
            entity_id=req.id,
            after_state={"status": req.status, "host": host_user_id, "visitor": visitor.id},
        )

        queue_notification(
            recipient_user_id=host_user_id,
            subject=f"New Visit Request: {visitor.name}",
            body=f"{visitor.name} has requested a visit on {start_time.strftime('%Y-%m-%d %H:%M')} for {req.purpose}.",
        )

    return req

    return req


@transaction.atomic
def decide_visit_request(
    actor_principal: Any,
    request_id: int,
    action: str,  # "approve" or "reject"
    reason: str = "",
) -> VisitRequest:
    """Host or Department Approver decision on visit request."""
    req = VisitRequest.objects.select_for_update().get(id=request_id)
    actor_role = actor_principal.active_role or (actor_principal.roles[0] if actor_principal.roles else "visitor")

    # Host cannot approve own visit
    primary_link = req.visitors.filter(is_primary=True).first()
    actor_email = getattr(actor_principal, "email", "").strip()
    if primary_link and actor_email and primary_link.visitor.email:
        if actor_email.lower() == primary_link.visitor.email.strip().lower():
            br.assert_host_not_visitor(req.host_user_id, actor_principal.user_id)

    before_state = {"status": req.status}

    if action == "approve":
        if req.status == sm.PENDING_HOST_APPROVAL:
            # Check if second approval needed
            if req.requires_second_approval and actor_role not in (sm.DEPT_APPROVER, sm.SECURITY_ADMIN, sm.ADMIN, sm.SUPER_ADMIN):
                sm.resolve(req.status, sm.PENDING_SECOND_APPROVAL, actor_role)
                req.status = sm.PENDING_SECOND_APPROVAL
                req.host_decision_at = timezone.now()
                req.save()
                log_audit(actor_principal.user_id, str(actor_principal), "ESCALATE_SECOND_APPROVAL", "VisitRequest", req.id, before_state, {"status": req.status})
                return req

            # Host approves directly
            sm.resolve(req.status, sm.APPROVED, actor_role)
            req.status = sm.APPROVED
            req.host_decision_at = timezone.now()

        elif req.status in (sm.PENDING_SECOND_APPROVAL, sm.PENDING_ADMIN_CONTINGENCY):
            target_to = sm.APPROVED
            sm.resolve(req.status, target_to, actor_role)
            req.status = target_to
            req.second_approver_user_id = actor_principal.user_id
            req.second_decision_at = timezone.now()

        else:
            sm.resolve(req.status, sm.APPROVED, actor_role)

        req.save()

        # Issue passes automatically upon approval
        issue_passes_for_request(actor_principal, req)
        req.status = sm.PASS_ISSUED
        req.save()

        queue_notification(
            recipient_email=primary_link.visitor.email if primary_link else "",
            subject="Your Visit Request Has Been Approved",
            body=f"Your visit on {req.start_time.strftime('%Y-%m-%d')} has been approved. A pass has been issued.",
        )

    elif action == "reject":
        if not reason.strip():
            raise GuardFailedError("has_rejection_reason", "Rejection justification is mandatory.")

        sm.resolve(req.status, sm.REJECTED, actor_role)
        req.status = sm.REJECTED
        req.rejection_reason = reason.strip()
        req.save()

        queue_notification(
            recipient_email=primary_link.visitor.email if primary_link else "",
            subject="Visit Request Rejected",
            body=f"Your visit request has been rejected. Reason: {reason}",
        )

    log_audit(
        who_user_id=actor_principal.user_id,
        who_label=str(actor_principal),
        action=f"DECIDE_VISIT_{action.upper()}",
        entity_type="VisitRequest",
        entity_id=req.id,
        before_state=before_state,
        after_state={"status": req.status, "reason": req.rejection_reason},
        reason=reason,
    )

    return req


@transaction.atomic
def issue_passes_for_request(
    actor_principal: Any,
    req: VisitRequest,
    is_multi_entry: bool = False,
) -> list[VisitPass]:
    """Generate unguessable cryptographically secure QR passes for all visitors in the request."""
    passes = []
    for link in req.visitors.all():
        token = f"VMS-{uuid.uuid4().hex}"
        vpass = VisitPass.objects.create(
            request=req,
            visitor=link.visitor,
            token=token,
            pass_type=req.visit_type,
            is_multi_entry=is_multi_entry,
            valid_from=req.start_time,
            valid_to=req.end_time,
            status="active",
            issued_by_user_id=getattr(actor_principal, "user_id", None),
        )
        passes.append(vpass)

        # Notify visitor of QR pass
        queue_notification(
            recipient_email=link.visitor.email,
            recipient_phone=link.visitor.phone,
            subject=f"Visitor Pass: {link.visitor.name}",
            body=f"Your visitor pass token is {token}. Present this at the gate between {req.start_time} and {req.end_time}.",
        )

    return passes


@transaction.atomic
def cancel_visit_request(
    actor_principal: Any,
    request_id: int,
    reason: str = "",
) -> VisitRequest:
    """Cancel a visit request prior to check-in."""
    req = VisitRequest.objects.select_for_update().get(id=request_id)
    actor_role = actor_principal.active_role or (actor_principal.roles[0] if actor_principal.roles else "visitor")

    before_state = {"status": req.status}
    sm.resolve(req.status, sm.CANCELLED, actor_role)

    req.status = sm.CANCELLED
    req.save()

    # Revoke any issued passes
    VisitPass.objects.filter(request=req, status="active").update(status="revoked")

    log_audit(
        who_user_id=actor_principal.user_id,
        who_label=str(actor_principal),
        action="CANCEL_VISIT_REQUEST",
        entity_type="VisitRequest",
        entity_id=req.id,
        before_state=before_state,
        after_state={"status": req.status},
        reason=reason,
    )

    return req


@transaction.atomic
def extend_visit_request(
    actor_principal: Any,
    request_id: int,
    additional_minutes: int,
    reason: str = "",
) -> VisitRequest:
    """Extend visit duration (Workflow G / BR-194)."""
    policy = get_active_policy()
    req = VisitRequest.objects.select_for_update().get(id=request_id)

    new_end = req.end_time + timedelta(minutes=additional_minutes)
    new_duration = req.expected_duration_minutes + additional_minutes

    br.validate_visit_duration(new_duration, policy.max_visit_duration_hours)

    before_state = {"end_time": req.end_time.isoformat(), "duration": req.expected_duration_minutes}
    req.end_time = new_end
    req.expected_duration_minutes = new_duration
    req.save()

    # Extend active pass validity window
    VisitPass.objects.filter(request=req, status="active").update(valid_to=new_end)

    log_audit(
        who_user_id=actor_principal.user_id,
        who_label=str(actor_principal),
        action="EXTEND_VISIT",
        entity_type="VisitRequest",
        entity_id=req.id,
        before_state=before_state,
        after_state={"end_time": req.end_time.isoformat(), "duration": req.expected_duration_minutes},
        reason=reason,
    )

    return req


@transaction.atomic
def check_in_visitor(
    actor_principal: Any,
    pass_token: str,
    gate_id: int,
    zone_id: int | None = None,
    override: bool = False,
    override_reason: str = "",
) -> CheckInOutLog:
    """Guard scans QR pass and checks in visitor at gate."""
    now = timezone.now()
    gate = Gate.objects.get(id=gate_id)
    actor_role = actor_principal.active_role or "security_guard"

    vpass = VisitPass.objects.select_for_update().get(token=pass_token)
    req = VisitRequest.objects.select_for_update().get(id=vpass.request_id)
    visitor = vpass.visitor

    # Pass must be active
    if vpass.status != "active":
        raise PassAlreadyUsedError(f"Pass is not active (current status: {vpass.status}).")

    # Time window validation (BR-190)
    if not override:
        br.validate_pass_window(now, vpass.valid_from, vpass.valid_to)

    # Re-screen against blacklist at gate (BR-112, BR-116)
    active_bl = list(BlacklistEntry.objects.filter(is_active=True).values())
    try:
        br.screen_blacklist(visitor.name, visitor.phone, visitor.id_hash, active_bl)
    except BlacklistMatchError as exc:
        Incident.objects.create(
            request=req,
            visitor=visitor,
            gate=gate,
            severity="critical",
            category="blacklist_attempt",
            description=f"Blacklisted person attempted check-in: {visitor.name} ({exc.reason})",
            reported_by_user_id=actor_principal.user_id,
        )
        log_audit(
            who_user_id=actor_principal.user_id,
            who_label=str(actor_principal),
            action="GATE_CHECK_IN_BLOCKED_BLACKLIST",
            entity_type="VisitPass",
            entity_id=vpass.id,
            reason=exc.reason,
        )
        raise

    # Zone capacity enforcement
    zone = None
    target_zone_id = zone_id or (req.permitted_zones.values_list("zone_id", flat=True).first())
    if target_zone_id:
        zone = Zone.objects.select_for_update().get(id=target_zone_id)
        br.validate_zone_capacity(zone.name, zone.current_occupancy, zone.max_capacity)
        zone.current_occupancy += 1
        zone.save()

    # State transition
    sm.resolve(req.status, sm.ON_SITE, actor_role)
    req.status = sm.ON_SITE
    req.save()

    # Update individual visitor status
    link = VisitVisitor.objects.get(request=req, visitor=visitor)
    link.status = "on_site"
    link.checked_in_at = now
    link.save()

    # Record check-in log
    log = CheckInOutLog.objects.create(
        pass_record=vpass,
        visitor=visitor,
        request=req,
        gate=gate,
        zone=zone,
        action="check_in",
        guard_user_id=actor_principal.user_id,
        timestamp=now,
        is_manual_override=override,
        override_reason=override_reason,
    )

    # Audit & Host notification
    log_audit(
        who_user_id=actor_principal.user_id,
        who_label=str(actor_principal),
        action="GATE_CHECK_IN",
        entity_type="VisitRequest",
        entity_id=req.id,
        after_state={"status": req.status, "gate": gate.code, "zone": zone.code if zone else None},
    )

    queue_notification(
        recipient_user_id=req.host_user_id,
        subject=f"Visitor Arrived: {visitor.name}",
        body=f"Your visitor {visitor.name} has arrived and checked in at {gate.name}.",
    )

    return log


@transaction.atomic
def check_out_visitor(
    actor_principal: Any,
    pass_token: str,
    gate_id: int,
    notes: str = "",
) -> CheckInOutLog:
    """Guard checks out visitor at gate."""
    now = timezone.now()
    gate = Gate.objects.get(id=gate_id)
    actor_role = actor_principal.active_role or "security_guard"

    vpass = VisitPass.objects.select_for_update().get(token=pass_token)
    req = VisitRequest.objects.select_for_update().get(id=vpass.request_id)
    visitor = vpass.visitor

    if req.status not in (sm.ON_SITE, sm.OVERSTAY):
        raise VmsDomainError(
            f"Cannot check out visit in status '{req.status}' (must be on_site or overstay).",
            code="not_on_site",
        )

    # Zone capacity decrement
    primary_zone_id = req.permitted_zones.values_list("zone_id", flat=True).first()
    zone = None
    if primary_zone_id:
        zone = Zone.objects.select_for_update().get(id=primary_zone_id)
        if zone.current_occupancy > 0:
            zone.current_occupancy -= 1
            zone.save()

    # Pass closure
    if not vpass.is_multi_entry:
        vpass.status = "completed"
        vpass.save()

    # Update individual visitor status
    link = VisitVisitor.objects.get(request=req, visitor=visitor)
    link.status = "completed"
    link.checked_out_at = now
    link.save()

    # If all visitors in request have completed, transition request to COMPLETED
    all_done = not req.visitors.exclude(status="completed").exists()
    if all_done:
        target = sm.COMPLETED
        sm.resolve(req.status, target, actor_role)
        req.status = target
        req.save()

    # Verify declared items out
    DeclaredItem.objects.filter(request=req).update(is_verified_out=True)

    # Record check-out log
    log = CheckInOutLog.objects.create(
        pass_record=vpass,
        visitor=visitor,
        request=req,
        gate=gate,
        zone=zone,
        action="check_out",
        guard_user_id=actor_principal.user_id,
        timestamp=now,
        notes=notes,
    )

    # Audit & Host notification
    log_audit(
        who_user_id=actor_principal.user_id,
        who_label=str(actor_principal),
        action="GATE_CHECK_OUT",
        entity_type="VisitRequest",
        entity_id=req.id,
        after_state={"status": req.status, "gate": gate.code},
    )

    queue_notification(
        recipient_user_id=req.host_user_id,
        subject=f"Visitor Departed: {visitor.name}",
        body=f"Your visitor {visitor.name} has checked out at {gate.name}.",
    )

    return log


@transaction.atomic
def register_walkin(
    actor_principal: Any,
    data: Mapping[str, Any],
) -> tuple[VisitRequest, VisitPass]:
    """Walk-in registration at gate by Security Guard or Receptionist (Workflow C)."""
    now = timezone.now()
    policy = get_active_policy()

    # Mandatory fields
    for field in ["name", "phone", "id_type", "id_number", "purpose", "host_user_id"]:
        if not data.get(field):
            raise VmsDomainError(f"Field '{field}' is required for walk-in registration.", code="missing_field")

    phone = str(data["phone"]).strip()
    name = str(data["name"]).strip()
    id_num = str(data["id_number"]).strip()
    id_h = hash_id(id_num)
    host_user_id = int(data["host_user_id"])

    # Blacklist check (BR-051)
    active_bl = list(BlacklistEntry.objects.filter(is_active=True).values())
    br.screen_blacklist(name, phone, id_h, active_bl)

    # Create Visitor
    visitor, _ = Visitor.objects.update_or_create(
        id_hash=id_h,
        defaults={
            "name": name,
            "phone": phone,
            "email": str(data.get("email", "")).strip(),
            "id_type": str(data["id_type"]),
            "masked_id": mask_id(id_num),
            "photo_url": str(data.get("photo_url", "")).strip(),
            "consent_given": True,
            "consent_timestamp": now,
        },
    )

    duration_minutes = int(data.get("duration_minutes", 120))
    start_time = now
    end_time = now + timedelta(minutes=duration_minutes)

    # Create walk-in visit request (approved or awaiting host confirmation)
    immediate_entry = bool(data.get("host_confirmed_verbally", True))
    initial_status = sm.APPROVED if immediate_entry else sm.PENDING_HOST_APPROVAL

    req = VisitRequest.objects.create(
        host_user_id=host_user_id,
        purpose=str(data["purpose"]),
        visit_type="walk_in",
        start_time=start_time,
        end_time=end_time,
        expected_duration_minutes=duration_minutes,
        status=initial_status,
    )

    VisitVisitor.objects.create(request=req, visitor=visitor, is_primary=True, status="approved" if immediate_entry else "pending")

    # Issue pass only if verbally confirmed
    if immediate_entry:
        passes = issue_passes_for_request(actor_principal, req)
        vpass = passes[0]
        req.status = sm.PASS_ISSUED
        req.save()
    else:
        vpass = None

    # Log audit
    log_audit(
        who_user_id=actor_principal.user_id,
        who_label=str(actor_principal),
        action="REGISTER_WALKIN",
        entity_type="VisitRequest",
        entity_id=req.id,
        after_state={"status": req.status, "pass_token": vpass.token if vpass else None},
    )

    queue_notification(
        recipient_user_id=host_user_id,
        subject=f"Walk-in Visitor at Gate: {visitor.name}",
        body=f"{visitor.name} has arrived at the gate requesting to meet you for '{req.purpose}'.",
    )

    return req, vpass
