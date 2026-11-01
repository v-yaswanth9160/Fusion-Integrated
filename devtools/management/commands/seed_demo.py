"""Demo fixtures.

Lives in `devtools` rather than inside a module: seeding is cross-cutting and
would otherwise make one module import three others' models. `devtools` is a
tool, not a bounded context, so .importlinter exempts it explicitly.
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

from modules.directory.models import UserRef
from modules.placement.models import Application, Company, JobPosting
from modules.vms.models import (
    BlacklistEntry,
    CheckInOutLog,
    Gate,
    Visitor,
    VisitPass,
    VisitPolicy,
    VisitRequest,
    VisitVisitor,
    VisitZone,
    Zone,
)


class Command(BaseCommand):
    help = "Load demo data (idempotent)"

    @transaction.atomic
    def handle(self, *args, **opts):
        for uid, name, kind, disc in [
            (1001, "Asha Verma", "student", "CSE"),
            (1002, "Bo Li", "student", "CSE"),
            (1003, "Chandra Rao", "student", "ECE"),
            (9001, "Dr. Meera Nair", "faculty", ""),
        ]:
            UserRef.objects.update_or_create(
                user_id=uid,
                defaults={
                    "username": f"u{uid}",
                    "display_name": name,
                    "kind": kind,
                    "discipline": disc,
                    "batch_year": 2023 if kind == "student" else None,
                },
            )

        acme, _ = Company.objects.update_or_create(
            slug="acme",
            defaults={"name": "Acme Corp", "sector": "IT", "tier_rank": 1, "status": "active"},
        )

        posting, _ = JobPosting.objects.update_or_create(
            company=acme,
            title="SDE-1",
            placement_year="2026-27",
            defaults={
                "description": "Software Development Engineer 1 position.",
                "ctc_lpa": "18.00",
                "seats": 4,
                "status": "published",
                "eligibility_rule": {
                    "all": [{"gte": ["cpi", 7.0]}, {"in": ["discipline", ["CSE", "ECE"]]}]
                },
                "eligibility_rule_locked_at": timezone.now(),
                "opens_at": timezone.now(),
                "closes_at": timezone.now() + timedelta(days=14),
                "created_by_user_id": 9001,
            },
        )

        for uid, status in [(1001, "submitted"), (1002, "under_review")]:
            Application.objects.update_or_create(
                posting=posting,
                user_id=uid,
                defaults={
                    "status": status,
                    "cpi_at_apply": "8.10",
                    "eligibility_snapshot": {"is_eligible": True},
                    "applied_at": timezone.now(),
                },
            )

        # --- VMS Demo Fixtures ---
        # Users for every role
        for uid, name, kind, dept in [
            (9001, "Dr. Meera Nair", "faculty", "CSE"),
            (9002, "Dr. Rajesh Kumar", "faculty", "Dean Academic"),
            (3001, "Ramesh Singh", "staff", "Security Guard"),
            (4001, "Pooja Sharma", "staff", "Reception"),
            (5001, "Vikram Patel", "staff", "Security Admin"),
            (6001, "Sunita Rao", "staff", "Auditor"),
        ]:
            UserRef.objects.update_or_create(
                user_id=uid,
                defaults={
                    "username": f"u{uid}",
                    "display_name": name,
                    "kind": kind,
                    "department": dept,
                    "email": f"u{uid}@institute.ac.in",
                    "is_active": True,
                },
            )

        # Global Visit Policy
        VisitPolicy.objects.update_or_create(
            version=1,
            defaults={
                "is_active": True,
                "max_visit_duration_hours": 8,
                "advance_booking_limit_days": 30,
                "daily_host_visitor_cap": 5,
                "walkin_host_timeout_minutes": 15,
                "retention_period_days": 365,
                "overstay_threshold_minutes": 15,
                "require_second_approval_for_groups_above": 5,
                "allow_recurring_visits": True,
            },
        )

        # Campus Gates
        main_gate, _ = Gate.objects.update_or_create(
            code="MAIN",
            defaults={"name": "Main Entrance Gate", "description": "Primary campus entrance", "is_active": True},
        )
        Gate.objects.update_or_create(
            code="NORTH",
            defaults={"name": "North Gate", "description": "North campus entrance/exit", "is_active": True},
        )

        # Campus Zones
        acad_zone, _ = Zone.objects.update_or_create(
            code="ACAD",
            defaults={"name": "Academic Complex", "is_restricted": False, "max_capacity": 200, "is_active": True},
        )
        Zone.objects.update_or_create(
            code="SERVER_DC",
            defaults={"name": "Data Center & Server Room", "is_restricted": True, "max_capacity": 10, "is_active": True},
        )

        # Blacklist Entry
        BlacklistEntry.objects.update_or_create(
            name="Devendra Kumar",
            phone="9988776655",
            defaults={
                "email": "devendra@badactor.local",
                "id_type": "aadhaar",
                "id_hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
                "reason": "Repeated misconduct and trespassing in hostel residential zone",
                "severity": "block",
                "added_by_user_id": 5001,
                "is_active": True,
            },
        )

        # Sample Visitors & Visits
        visitor1, _ = Visitor.objects.update_or_create(
            phone="9876543210",
            defaults={
                "name": "Amitabh Joshi",
                "email": "amitabh@techcorp.in",
                "organisation": "Tech Solutions Pvt Ltd",
                "id_type": "aadhaar",
                "id_hash": "hash_amitabh_1234",
                "masked_id": "XXXX-XXXX-1234",
                "consent_given": True,
                "consent_version": "v1.0",
                "consent_timestamp": timezone.now(),
            },
        )

        visit1, _ = VisitRequest.objects.update_or_create(
            purpose="Guest Lecture on Cloud Infrastructure",
            host_user_id=9001,
            defaults={
                "visit_type": "single",
                "start_time": timezone.now() + timedelta(hours=2),
                "end_time": timezone.now() + timedelta(hours=5),
                "expected_duration_minutes": 180,
                "status": "pending_host_approval",
                "requires_second_approval": False,
            },
        )
        VisitVisitor.objects.update_or_create(request=visit1, visitor=visitor1, defaults={"is_primary": True, "status": "pending"})
        VisitZone.objects.update_or_create(request=visit1, zone=acad_zone)

        # Approved visit with active pass
        visitor2, _ = Visitor.objects.update_or_create(
            phone="9123456780",
            defaults={
                "name": "Prof. Sunita Menon",
                "email": "smenon@partner-univ.ac.in",
                "organisation": "National Research Institute",
                "id_type": "pan",
                "id_hash": "hash_sunita_5678",
                "masked_id": "XXXXX5678X",
                "consent_given": True,
                "consent_version": "v1.0",
                "consent_timestamp": timezone.now(),
            },
        )

        visit2, _ = VisitRequest.objects.update_or_create(
            purpose="Curriculum Review Meeting",
            host_user_id=9001,
            defaults={
                "visit_type": "single",
                "start_time": timezone.now() - timedelta(hours=1),
                "end_time": timezone.now() + timedelta(hours=3),
                "expected_duration_minutes": 240,
                "status": "pass_issued",
                "requires_second_approval": False,
            },
        )
        VisitVisitor.objects.update_or_create(request=visit2, visitor=visitor2, defaults={"is_primary": True, "status": "approved"})
        VisitZone.objects.update_or_create(request=visit2, zone=acad_zone)
        VisitPass.objects.update_or_create(
            request=visit2,
            visitor=visitor2,
            defaults={
                "token": "VMS-DEMO-PASS-TOKEN-001",
                "pass_type": "single",
                "valid_from": timezone.now() - timedelta(hours=1),
                "valid_to": timezone.now() + timedelta(hours=3),
                "status": "active",
                "is_multi_entry": False,
            },
        )

        # On-site visit
        visitor3, _ = Visitor.objects.update_or_create(
            phone="9988001122",
            defaults={
                "name": "Kiran Deshmukh",
                "email": "kiran@vendor.com",
                "organisation": "Precision Instruments Ltd",
                "id_type": "passport",
                "id_hash": "hash_kiran_9012",
                "masked_id": "XXXXXX9012",
                "consent_given": True,
                "consent_version": "v1.0",
                "consent_timestamp": timezone.now(),
            },
        )

        visit3, _ = VisitRequest.objects.update_or_create(
            purpose="Lab Equipment Maintenance",
            host_user_id=9001,
            defaults={
                "visit_type": "single",
                "start_time": timezone.now() - timedelta(hours=2),
                "end_time": timezone.now() + timedelta(hours=2),
                "expected_duration_minutes": 240,
                "status": "on_site",
                "requires_second_approval": False,
            },
        )
        VisitVisitor.objects.update_or_create(request=visit3, visitor=visitor3, defaults={"is_primary": True, "status": "checked_in"})
        VisitZone.objects.update_or_create(request=visit3, zone=acad_zone)
        pass3, _ = VisitPass.objects.update_or_create(
            request=visit3,
            visitor=visitor3,
            defaults={
                "token": "VMS-DEMO-PASS-TOKEN-002",
                "pass_type": "single",
                "valid_from": timezone.now() - timedelta(hours=2),
                "valid_to": timezone.now() + timedelta(hours=2),
                "status": "active",
                "is_multi_entry": False,
            },
        )
        CheckInOutLog.objects.update_or_create(
            pass_record=pass3,
            visitor=visitor3,
            request=visit3,
            gate=main_gate,
            action="check_in",
            defaults={
                "guard_user_id": 3001,
                "timestamp": timezone.now() - timedelta(hours=1, minutes=45),
                "is_manual_override": False,
            },
        )

        self.stdout.write(self.style.SUCCESS("demo data loaded (including VMS fixtures)"))
