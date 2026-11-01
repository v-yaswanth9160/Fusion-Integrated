"""VMS Scheduled Jobs."""
from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from modules.vms.models import Incident, Visitor, VisitPass, VisitPolicy, VisitRequest
from modules.vms.services.audit import log_audit

def expire_overdue_passes_job() -> int:
    now = timezone.now()
    with transaction.atomic():
        expired = VisitPass.objects.filter(status="active", valid_to__lt=now)
        req_ids = list(expired.values_list("request_id", flat=True).distinct())
        count = expired.update(status="expired")
        if req_ids:
            VisitRequest.objects.filter(id__in=req_ids, status="pass_issued").update(status="expired")
            log_audit(0, "SYSTEM_JOB", "AUTO_EXPIRE_PASSES", "VisitPass", 0, after_state={"expired_count": count})
    return count

def flag_overstay_visitors_job() -> int:
    now = timezone.now()
    policy = VisitPolicy.objects.filter(is_active=True).first()
    grace = policy.overstay_threshold_minutes if policy else 15
    cutoff = now - timedelta(minutes=grace)
    count = 0
    with transaction.atomic():
        overstays = VisitRequest.objects.filter(status="on_site", end_time__lt=cutoff)
        for req in overstays:
            req.status = "overstay"
            req.save(update_fields=["status"])
            Incident.objects.get_or_create(request=req, category="overstay", defaults={"severity": "high", "description": f"Visitor overstayed beyond {req.end_time.isoformat()}", "reported_by_user_id": 0})
            log_audit(0, "SYSTEM_JOB", "FLAG_OVERSTAY", "VisitRequest", req.id, after_state={"status": "overstay"})
            count += 1
    return count

def apply_retention_anonymisation_job() -> int:
    now = timezone.now()
    policy = VisitPolicy.objects.filter(is_active=True).first()
    retention_days = policy.retention_period_days if policy else 365
    cutoff = now - timedelta(days=retention_days)
    count = 0
    with transaction.atomic():
        visitors = Visitor.objects.filter(is_anonymized=False, created_at__lt=cutoff)
        for v in visitors:
            v.name, v.phone, v.email, v.photo_url, v.is_anonymized = "ANONYMIZED_VISITOR", "0000000000", "", "", True
            v.save()
            count += 1
    return count
