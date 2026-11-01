"""Tests for Celery scheduled jobs: pass expiry, overstay flagging, and retention anonymisation."""
from datetime import timedelta
import pytest
from django.utils import timezone

from modules.vms.models import (
    AuditLogEntry,
    Gate,
    Incident,
    Notification,
    Visitor,
    VisitPass,
    VisitPolicy,
    VisitRequest,
    VisitVisitor,
)
from modules.vms.services.jobs import (
    apply_retention_anonymisation_job,
    expire_overdue_passes_job,
    flag_overstay_visitors_job,
)

pytestmark = pytest.mark.django_db


def test_expire_overdue_passes_job():
    now = timezone.now()
    policy = VisitPolicy.objects.create(version=1, is_active=True)

    visitor = Visitor.objects.create(
        name="No Show Guest",
        phone="9911223344",
        id_type="aadhaar",
        masked_id="XXXX-1234",
        id_hash="dummy_hash_noshow",
    )
    req = VisitRequest.objects.create(
        host_user_id=101,
        purpose="Interview",
        start_time=now - timedelta(hours=3),
        end_time=now - timedelta(hours=1),  # Window closed in the past
        status="pass_issued",
    )
    vpass = VisitPass.objects.create(
        request=req,
        visitor=visitor,
        valid_from=now - timedelta(hours=3),
        valid_to=now - timedelta(hours=1),
        status="active",
    )

    # Run sweep
    count = expire_overdue_passes_job()
    assert count == 1

    vpass.refresh_from_db()
    req.refresh_from_db()
    assert vpass.status == "expired"
    assert req.status == "expired"

    # Running again is idempotent
    assert expire_overdue_passes_job() == 0


def test_flag_overstay_visitors_job():
    now = timezone.now()
    policy = VisitPolicy.objects.create(version=1, is_active=True, overstay_threshold_minutes=15)

    visitor = Visitor.objects.create(
        name="Overstay Guest",
        phone="9922334455",
        id_type="passport",
        masked_id="XXXX-5678",
        id_hash="dummy_hash_overstay",
    )
    req = VisitRequest.objects.create(
        host_user_id=101,
        purpose="Workshop",
        start_time=now - timedelta(hours=4),
        end_time=now - timedelta(hours=1),  # 60 mins ago (> 15 min threshold)
        status="on_site",
    )
    VisitVisitor.objects.create(request=req, visitor=visitor, is_primary=True, status="on_site")

    # Run sweep
    count = flag_overstay_visitors_job()
    assert count == 1

    req.refresh_from_db()
    assert req.status == "overstay"

    # Incident created
    inc = Incident.objects.filter(request=req, category="overstay").first()
    assert inc is not None
    assert inc.severity == "high"

    # Notification sent
    assert Notification.objects.filter(recipient_user_id=101, subject__icontains="OVERSTAY").exists()


def test_apply_retention_anonymisation_job():
    now = timezone.now()
    policy = VisitPolicy.objects.create(version=1, is_active=True, retention_period_days=30)

    # Old visitor from 40 days ago
    old_visitor = Visitor.objects.create(
        name="Old Visitor",
        phone="9933445566",
        email="old@example.com",
        id_type="pan",
        masked_id="XXXX-9999",
        id_hash="dummy_hash_old",
        is_anonymized=False,
    )
    req = VisitRequest.objects.create(
        host_user_id=101,
        purpose="Past Conference",
        start_time=now - timedelta(days=45),
        end_time=now - timedelta(days=40),
        status="completed",
    )
    VisitVisitor.objects.create(request=req, visitor=old_visitor, is_primary=True, status="completed")

    # Run retention sweep
    count = apply_retention_anonymisation_job()
    assert count == 1

    old_visitor.refresh_from_db()
    assert old_visitor.is_anonymized is True
    assert "[ANONYMIZED" in old_visitor.name
    assert old_visitor.phone == "0000000000"
    assert old_visitor.masked_id == "XXXX-XXXX"

    # Audit log exists
    audit = AuditLogEntry.objects.filter(action="DATA_RETENTION_ANONYMIZED").first()
    assert audit is not None
