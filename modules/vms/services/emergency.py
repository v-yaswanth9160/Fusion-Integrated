"""Emergency Muster Service."""
import uuid
from django.db import transaction
from django.utils import timezone
from modules.vms.models import CheckInOutLog, EmergencyMuster, MusterRollCall
from modules.vms.services.audit import log_audit

@transaction.atomic
def trigger_emergency_muster(actor_principal, notes=""):
    muster = EmergencyMuster.objects.create(session_id=f"MUSTER-{uuid.uuid4().hex[:8].upper()}", triggered_by_user_id=actor_principal.user_id, notes=notes)
    active_logs = CheckInOutLog.objects.filter(action="check_in", pass_record__status="active").select_related("visitor", "zone")
    seen, roll_calls = set(), []
    for log in active_logs:
        if log.visitor_id not in seen:
            seen.add(log.visitor_id)
            roll_calls.append(MusterRollCall(muster=muster, visitor=log.visitor, visitor_name=log.visitor.name, zone_name=log.zone.name if log.zone else "Main Campus", status="unaccounted"))
    if roll_calls:
        MusterRollCall.objects.bulk_create(roll_calls)
    muster.total_on_site, muster.unaccounted_count = len(roll_calls), len(roll_calls)
    muster.save(update_fields=["total_on_site", "unaccounted_count"])
    log_audit(actor_principal.user_id, str(actor_principal), "TRIGGER_EMERGENCY_MUSTER", "EmergencyMuster", muster.id, after_state={"total_on_site": muster.total_on_site})
    return muster

@transaction.atomic
def record_roll_call(actor_principal, muster_id, visitor_id, status, notes=""):
    rc = MusterRollCall.objects.select_for_update().get(muster_id=muster_id, visitor_id=visitor_id)
    rc.status, rc.marked_by_user_id, rc.marked_at, rc.notes = status, actor_principal.user_id, timezone.now(), notes
    rc.save()
    muster = EmergencyMuster.objects.select_for_update().get(id=muster_id)
    muster.safe_count = muster.records.filter(status="safe").count()
    muster.unaccounted_count = muster.records.filter(status="unaccounted").count()
    muster.save(update_fields=["safe_count", "unaccounted_count"])
    return rc

@transaction.atomic
def end_emergency_muster(actor_principal, muster_id):
    muster = EmergencyMuster.objects.select_for_update().get(id=muster_id)
    muster.status, muster.ended_at = "completed", timezone.now()
    muster.save()
    log_audit(actor_principal.user_id, str(actor_principal), "END_EMERGENCY_MUSTER", "EmergencyMuster", muster.id, after_state={"safe": muster.safe_count, "unaccounted": muster.unaccounted_count})
    return muster
