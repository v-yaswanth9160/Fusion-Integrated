"""Notification queue service."""
from modules.vms.models import Notification

def queue_notification(recipient_user_id=None, recipient_email="", subject="", body=""):
    return Notification.objects.create(
        recipient_user_id=recipient_user_id, recipient_email=recipient_email, subject=subject, body=body,
    )
