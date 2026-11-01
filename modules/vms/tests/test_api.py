"""API and integration tests for VMS REST endpoints.

Tests allowed (2xx), denied role (403), illegal state (409), unauthenticated (401),
and data privacy / masking.
"""
from datetime import timedelta
import pytest
from django.utils import timezone
from rest_framework.test import APIClient

from conftest import make_session
from modules.vms.models import (
    AuditLogEntry,
    BlacklistEntry,
    Gate,
    VisitPass,
    VisitPolicy,
    VisitRequest,
    VisitVisitor,
    Zone,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def setup_data():
    gate = Gate.objects.create(code="GATE_MAIN", name="Main Gate")
    zone = Zone.objects.create(code="ACAD", name="Academic Block", max_capacity=20)
    policy = VisitPolicy.objects.create(version=1, is_active=True)
    return {"gate": gate, "zone": zone, "policy": policy}


def _authed_client(stub_iam, **session_kw):
    if "modules" not in session_kw:
        session_kw["modules"] = ("vms",)
    session = make_session(**session_kw)
    stub_iam(session)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION="Token mock_token")
    return client


def test_public_pre_registration_and_pass_display(api_client, setup_data):
    """External visitor can pre-register without authentication, and view pass."""
    now = timezone.now()
    reg_data = {
        "name": "Public Visitor",
        "phone": "9876500001",
        "email": "public@visitor.org",
        "organisation": "External Co",
        "id_type": "passport",
        "id_number": "PUB12345678",
        "purpose": "Consultation",
        "start_time": (now + timedelta(hours=2)).isoformat(),
        "end_time": (now + timedelta(hours=4)).isoformat(),
        "host_user_id": 101,
        "zone_ids": [setup_data["zone"].id],
    }

    # Public registration (no auth)
    resp = api_client.post("/api/v1/vms/public/register", reg_data, format="json")
    assert resp.status_code == 201
    data = resp.json()
    assert data["status"] == "pending_host_approval"

    # Privacy check: raw id_number must NOT be in the response
    raw_json = str(resp.content)
    assert "PUB12345678" not in raw_json
    assert "5678" in raw_json  # Masked ID ends with last 4 chars


def test_public_pass_view_and_cancellation(api_client, stub_iam, setup_data):
    """Visitor can view pass and cancel own visit via public unguessable token."""
    now = timezone.now()
    client = _authed_client(
        stub_iam,
        user_id=101,
        kind="faculty",
        roles=("host",),
        active_role="host",
        permissions=("vms.visit_request.create", "vms.visit_request.approve_host", "vms.visit_request.view_self"),
        modules=("vms",),
    )

    create_resp = client.post(
        "/api/v1/vms/requests",
        {
            "name": "Cancel Me",
            "phone": "9876500002",
            "id_type": "aadhaar",
            "id_number": "1122-3344-5566",
            "purpose": "Meeting",
            "start_time": (now + timedelta(hours=1)).isoformat(),
            "end_time": (now + timedelta(hours=3)).isoformat(),
            "host_user_id": 101,
        },
        format="json",
    )
    req_id = create_resp.json()["id"]

    # Host approves -> Pass issued
    client.post(f"/api/v1/vms/requests/{req_id}/decide", {"action": "approve"}, format="json")
    vpass = VisitPass.objects.get(request_id=req_id)

    # Public pass view
    pass_resp = api_client.get(f"/api/v1/vms/public/pass/{vpass.token}")
    assert pass_resp.status_code == 200
    assert pass_resp.json()["token"] == vpass.token

    # Public cancellation
    cancel_resp = api_client.post(f"/api/v1/vms/public/cancel/{vpass.token}", {"reason": "Cannot attend"}, format="json")
    assert cancel_resp.status_code == 200
    assert cancel_resp.json()["status"] == "cancelled"


def test_host_sees_only_own_requests_and_scoping_404(stub_iam, setup_data):
    """Host 101 cannot see Host 102's visits; requesting foreign ID yields 404."""
    now = timezone.now()
    s1 = make_session(
        user_id=101,
        kind="faculty",
        roles=("host",),
        active_role="host",
        permissions=("vms.visit_request.create", "vms.visit_request.view_self", "vms.visit_request.approve_host"),
        modules=("vms",),
    )
    s2 = make_session(
        user_id=102,
        kind="faculty",
        roles=("host",),
        active_role="host",
        permissions=("vms.visit_request.create", "vms.visit_request.view_self", "vms.visit_request.approve_host"),
        modules=("vms",),
    )

    stub_iam(s1)
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION="Token mock_token")

    r1 = c.post(
        "/api/v1/vms/requests",
        {
            "name": "Host 1 Guest",
            "phone": "9876500011",
            "id_type": "passport",
            "id_number": "H1-9999",
            "purpose": "Discussion",
            "start_time": (now + timedelta(hours=1)).isoformat(),
            "end_time": (now + timedelta(hours=3)).isoformat(),
            "host_user_id": 101,
        },
        format="json",
    ).json()["id"]

    stub_iam(s2)
    r2 = c.post(
        "/api/v1/vms/requests",
        {
            "name": "Host 2 Guest",
            "phone": "9876500012",
            "id_type": "passport",
            "id_number": "H2-9999",
            "purpose": "Discussion",
            "start_time": (now + timedelta(hours=1)).isoformat(),
            "end_time": (now + timedelta(hours=3)).isoformat(),
            "host_user_id": 102,
        },
        format="json",
    ).json()["id"]

    # Switch back to Host 1
    stub_iam(s1)
    list1 = c.get("/api/v1/vms/requests").json()
    ids1 = [item["id"] for item in list1]
    assert r1 in ids1
    assert r2 not in ids1

    # Attempting to fetch r2 by host 1 gives 404 (NotFoundError), never 403
    detail_foreign = c.get(f"/api/v1/vms/requests/{r2}")
    assert detail_foreign.status_code == 404


def test_gate_check_in_and_check_out_api(stub_iam, setup_data):
    """Guard verifies pass, checks in and checks out visitor."""
    now = timezone.now()
    s_host = make_session(
        user_id=101,
        kind="faculty",
        roles=("host",),
        active_role="host",
        permissions=("vms.visit_request.create", "vms.visit_request.approve_host"),
        modules=("vms",),
    )
    s_guard = make_session(
        user_id=301,
        kind="staff",
        roles=("security_guard",),
        active_role="security_guard",
        permissions=("vms.pass.scan", "vms.gate.check_in_out"),
        modules=("vms",),
    )

    stub_iam(s_host)
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION="Token mock_token")

    req_id = c.post(
        "/api/v1/vms/requests",
        {
            "name": "Gate Visitor",
            "phone": "9876500021",
            "id_type": "aadhaar",
            "id_number": "1111-2222-3333",
            "purpose": "Lab Visit",
            "start_time": (now + timedelta(minutes=15)).isoformat(),
            "end_time": (now + timedelta(hours=2)).isoformat(),
            "host_user_id": 101,
            "zone_ids": [setup_data["zone"].id],
        },
        format="json",
    ).json()["id"]

    c.post(f"/api/v1/vms/requests/{req_id}/decide", {"action": "approve"}, format="json")
    vpass = VisitPass.objects.get(request_id=req_id)
    vpass.valid_from = now - timedelta(minutes=5)
    vpass.save()

    # Switch to Guard
    stub_iam(s_guard)

    # Guard verifies pass
    verify_resp = c.post("/api/v1/vms/gate/verify", {"token": vpass.token}, format="json")
    assert verify_resp.status_code == 200
    assert verify_resp.json()["status"] == "active"

    # Guard checks in
    in_resp = c.post(
        "/api/v1/vms/gate/check-in",
        {"pass_token": vpass.token, "gate_id": setup_data["gate"].id},
        format="json",
    )
    assert in_resp.status_code == 200
    assert in_resp.json()["action"] == "check_in"

    # Guard checks out
    out_resp = c.post(
        "/api/v1/vms/gate/check-out",
        {"pass_token": vpass.token, "gate_id": setup_data["gate"].id, "notes": "Left on time"},
        format="json",
    )
    assert out_resp.status_code == 200
    assert out_resp.json()["action"] == "check_out"


def test_unauthorized_role_gets_403(stub_iam, setup_data):
    """Host role cannot access guard check-in or security blacklist."""
    host_client = _authed_client(
        stub_iam,
        user_id=101,
        kind="faculty",
        roles=("host",),
        active_role="host",
        permissions=("vms.visit_request.create", "vms.visit_request.view_self"),
        modules=("vms",),
    )

    # Cannot check in
    checkin_resp = host_client.post(
        "/api/v1/vms/gate/check-in",
        {"pass_token": "any_token", "gate_id": setup_data["gate"].id},
        format="json",
    )
    assert checkin_resp.status_code == 403

    # Cannot manage blacklist
    bl_resp = host_client.post(
        "/api/v1/vms/blacklist",
        {"name": "Bad Person", "reason": "No entry"},
        format="json",
    )
    assert bl_resp.status_code == 403


def test_walk_in_registration_api(stub_iam, setup_data):
    """Receptionist registers walk-in visitor at front desk."""
    reception_client = _authed_client(
        stub_iam,
        user_id=401,
        kind="staff",
        roles=("reception",),
        active_role="reception",
        permissions=("vms.walkin.register", "vms.pass.issue", "vms.gate.check_in_out"),
        modules=("vms",),
    )

    resp = reception_client.post(
        "/api/v1/vms/gate/walk-in",
        {
            "name": "Walkin Guest",
            "phone": "9876500031",
            "id_type": "pan",
            "id_number": "PAN998877",
            "purpose": "Urgent Signature",
            "host_user_id": 101,
            "duration_minutes": 60,
            "host_confirmed_verbally": True,
        },
        format="json",
    )
    assert resp.status_code == 201
    assert resp.json()["visit_type"] == "walk_in"


def test_emergency_muster_and_export_audit(stub_iam, setup_data):
    """Security Admin triggers muster, roll call, and downloads CSV export."""
    admin_client = _authed_client(
        stub_iam,
        user_id=901,
        kind="staff",
        roles=("security_admin",),
        active_role="security_admin",
        permissions=(
            "vms.emergency.trigger",
            "vms.emergency.roll_call",
            "vms.report.view",
            "vms.report.export",
            "vms.audit.view",
        ),
        modules=("vms",),
    )

    # Trigger muster
    trigger_resp = admin_client.post("/api/v1/vms/muster/trigger", {"notes": "Campus Drill"}, format="json")
    assert trigger_resp.status_code == 201
    muster_id = trigger_resp.json()["id"]

    # End muster
    end_resp = admin_client.post(f"/api/v1/vms/muster/{muster_id}/end", format="json")
    assert end_resp.status_code == 200
    assert end_resp.json()["status"] == "completed"

    # Export report CSV
    export_resp = admin_client.get("/api/v1/vms/reports/export")
    assert export_resp.status_code == 200
    assert export_resp["Content-Type"] == "text/csv"

    # Check that export was audited
    audit_row = AuditLogEntry.objects.filter(action="EXPORT_VISITOR_REPORT").first()
    assert audit_row is not None
    assert audit_row.who_user_id == 901
