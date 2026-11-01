"""VMS Pure Domain Errors."""


class VmsDomainError(Exception):
    code = "vms_domain_error"
    http_status = 422

    def __init__(self, message: str, code: str | None = None, details: list | None = None):
        super().__init__(message)
        self.message, self.code, self.details = message, code or self.code, details or []


class InvalidTransitionError(VmsDomainError):
    code, http_status = "invalid_transition", 409

    def __init__(self, frm: str, to: str):
        super().__init__(f"Cannot transition visit from '{frm}' to '{to}'.", code=self.code)
        self.frm, self.to = frm, to


class ActorNotAllowedError(VmsDomainError):
    code, http_status = "actor_not_allowed", 403

    def __init__(self, actor: str, frm: str, to: str):
        super().__init__(f"Actor '{actor}' not permitted to transition '{frm}' to '{to}'.", code=self.code)
        self.actor, self.frm, self.to = actor, frm, to


class GuardFailedError(VmsDomainError):
    code, http_status = "guard_failed", 409

    def __init__(self, guard: str, message: str = ""):
        super().__init__(message or f"Guard '{guard}' failed.", code=self.code)
        self.guard = guard


class BlacklistMatchError(VmsDomainError):
    code, http_status = "blacklist_denied", 403

    def __init__(self, name: str, reason: str, severity: str = "block"):
        super().__init__(f"Visitor '{name}' is blacklisted ({severity}): {reason}", code=self.code)
        self.name, self.reason, self.severity = name, reason, severity


class ZoneCapacityExceededError(VmsDomainError):
    code, http_status = "zone_capacity_exceeded", 409

    def __init__(self, zone_name: str, capacity: int):
        super().__init__(f"Zone '{zone_name}' reached capacity ({capacity}).", code=self.code)
        self.zone_name, self.capacity = zone_name, capacity


class SelfApprovalNotAllowedError(VmsDomainError):
    code, http_status = "self_approval_forbidden", 403

    def __init__(self, host_user_id: int):
        super().__init__(f"Host {host_user_id} cannot approve own visit.", code=self.code)
        self.host_user_id = host_user_id


class PassWindowInvalidError(VmsDomainError):
    code, http_status = "pass_window_invalid", 409


class PassAlreadyUsedError(VmsDomainError):
    code, http_status = "pass_already_used", 409
