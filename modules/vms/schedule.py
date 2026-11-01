"""Celery beat schedules and routing for VMS."""
from celery.schedules import crontab

BEAT_SCHEDULE = {
    "vms-expire-overdue-passes": {
        "task": "vms.expire_overdue_passes",
        "schedule": crontab(minute="*/5"),  # Every 5 minutes
    },
    "vms-flag-overstay-visitors": {
        "task": "vms.flag_overstay_visitors",
        "schedule": crontab(minute="*/10"),  # Every 10 minutes
    },
    "vms-retention-anonymisation": {
        "task": "vms.apply_retention_anonymisation",
        "schedule": crontab(hour=2, minute=30),  # Daily at 02:30 AM
    },
}

TASK_ROUTES = {
    "vms.*": {"queue": "vms"},
}
