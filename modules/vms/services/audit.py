"""Audit logging service."""
from modules.vms.models import AuditLogEntry

def log_audit(who_user_id, who_label, action, entity_type, entity_id, before_state=None, after_state=None, reason="", ip_address=None):
    return AuditLogEntry.objects.create(
        who_user_id=who_user_id, who_label=str(who_label), action=action,
        entity_type=entity_type, entity_id=entity_id, before_state=before_state or {},
        after_state=after_state or {}, reason=reason, ip_address=ip_address,
    )
