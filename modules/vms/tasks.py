"""Celery background tasks for VMS."""
from celery import shared_task

from modules.vms.services.jobs import (
    apply_retention_anonymisation_job,
    expire_overdue_passes_job,
    flag_overstay_visitors_job,
)


@shared_task(name="vms.expire_overdue_passes")
def expire_overdue_passes() -> int:
    """Expire passes whose validity window has passed without check-in."""
    return expire_overdue_passes_job()


@shared_task(name="vms.flag_overstay_visitors")
def flag_overstay_visitors() -> int:
    """Flag visitors remaining on-site past expected duration."""
    return flag_overstay_visitors_job()


@shared_task(name="vms.apply_retention_anonymisation")
def apply_retention_anonymisation() -> int:
    """Anonymize personal visitor data past retention window."""
    return apply_retention_anonymisation_job()
