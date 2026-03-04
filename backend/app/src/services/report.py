from datetime import datetime
import uuid

from pymongo import ReturnDocument

from src.extensions import mongo_client
from src.services.audit import AuditService
from src.services.preflight import PreflightService

REPORT_SCHEMA_VERSION = "1.0"

ROLES_CAN_FINALISE = {"senior_reviewer", "lab_director"}


class ReportError(Exception):
    pass


def _build_snapshot(db, sample_assay_id: str) -> dict:
    sample_assay = db.sample_assays.find_one({"sample_assay_id": sample_assay_id}) or {}
    sample = db.samples.find_one({"sample_id": sample_assay.get("sample_id")}) or {}
    callset = db.callsets.find_one({"callset_id": sample_assay.get("active_callset_id")}) or {}
    assay_config = db.assay_configs.find_one({"assay_id": sample_assay.get("assay_id")}) or {}

    for d in [sample, callset, assay_config, sample_assay]:
        d.pop("_id", None)

    snvs = list(db.snvs_raw.find({"sample_assay_id": sample_assay_id}, {"_id": 0}))
    cnvs = list(db.cnvs_raw.find({"sample_assay_id": sample_assay_id}, {"_id": 0}))
    svs = list(db.svs_raw.find({"sample_assay_id": sample_assay_id}, {"_id": 0}))
    biomarkers = db.biomarkers.find_one({"sample_assay_id": sample_assay_id}, {"_id": 0}) or {}

    return {
        "sample": sample,
        "assay": sample_assay,
        "assay_version": sample_assay.get("assay_version"),
        "callset_qc": callset.get("qc_metrics", {}),
        "snvs": snvs,
        "cnvs": cnvs,
        "svs": svs,
        "biomarkers": biomarkers,
        "knowledge_versions_used": {},
        "threshold_versions_used": {
            "assay_id": assay_config.get("assay_id"),
            "assay_version": assay_config.get("version"),
        },
    }


def _reportable_variants(variants: list) -> list:
    """Filter to concordant/resolved, non-artifact variants only."""
    out = []
    for v in variants:
        rc = v.get("review_current") or {}
        if rc.get("is_artifact"):
            continue
        if rc.get("consensus_status") in ("concordant", "resolved"):
            out.append(v)
    return out


class ReportService:

    @staticmethod
    def create_draft(
        sample_assay_id: str,
        created_by_user_id: str,
        created_by_username: str,
    ) -> dict:
        """Create a new draft report with a snapshot of current case state."""
        db = mongo_client.db

        if not db.sample_assays.find_one({"sample_assay_id": sample_assay_id}):
            raise ReportError("Sample assay not found.")

        existing = db.reports.find_one(
            {"sample_assay_id": sample_assay_id, "status": {"$in": ["draft", "pending_sign_off"]}}
        )
        if existing:
            raise ReportError(
                "An active draft or pending report already exists for this case. "
                "Finalise or discard it before creating a new one."
            )

        report_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat() + "Z"

        doc = {
            "report_id": report_id,
            "sample_assay_id": sample_assay_id,
            "report_schema_version": REPORT_SCHEMA_VERSION,
            "status": "draft",
            "report_type": "primary",
            "supersedes_report_id": None,
            "snapshot": _build_snapshot(db, sample_assay_id),
            "preflight_checks": PreflightService.run_checks(sample_assay_id),
            "sign_offs": [],
            "pdf_path": None,
            "json_path": None,
            "delivered_at": None,
            "delivered_to": None,
            "created_at": now,
            "created_by": created_by_user_id,
        }

        db.reports.insert_one(doc)
        doc.pop("_id", None)

        AuditService.log(
            event_type="report_created",
            target_collection="reports",
            target_id=report_id,
            payload={"sample_assay_id": sample_assay_id, "actor": created_by_username},
        )

        return doc

    @staticmethod
    def get_report(report_id: str) -> dict | None:
        db = mongo_client.db
        return db.reports.find_one({"report_id": report_id}, {"_id": 0})

    @staticmethod
    def get_reports_for_assay(sample_assay_id: str) -> list:
        db = mongo_client.db
        return list(
            db.reports.find(
                {"sample_assay_id": sample_assay_id},
                {"_id": 0, "snapshot": 0},  # exclude heavy snapshot from list view
            ).sort("created_at", -1)
        )

    @staticmethod
    def get_active_report(sample_assay_id: str) -> dict | None:
        """Return the most recent non-superseded report for an assay."""
        db = mongo_client.db
        return db.reports.find_one(
            {
                "sample_assay_id": sample_assay_id,
                "status": {"$nin": ["superseded"]},
            },
            {"_id": 0, "snapshot": 0},
            sort=[("created_at", -1)],
        )

    @staticmethod
    def add_signoff(
        report_id: str,
        actor_user_id: str,
        actor_username: str,
        actor_role: str,
    ) -> dict:
        """Add an electronic sign-off to a draft or pending report."""
        db = mongo_client.db

        report = db.reports.find_one({"report_id": report_id})
        if not report:
            raise ReportError("Report not found.")

        if report["status"] not in ("draft", "pending_sign_off"):
            raise ReportError(
                f"Cannot sign off a report with status '{report['status']}'."
            )

        existing_signoffs = report.get("sign_offs", [])
        if any(s["user_id"] == actor_user_id for s in existing_signoffs):
            raise ReportError("You have already signed off on this report.")

        signoff = {
            "user_id": actor_user_id,
            "username": actor_username,
            "role": actor_role,
            "signed_at": datetime.utcnow().isoformat() + "Z",
            "signature_type": "electronic",
        }

        updated = db.reports.find_one_and_update(
            {"report_id": report_id},
            {
                "$push": {"sign_offs": signoff},
                "$set": {"status": "pending_sign_off"},
            },
            return_document=ReturnDocument.AFTER,
            projection={"_id": 0, "snapshot": 0},
        )

        AuditService.log(
            event_type="report_signed",
            target_collection="reports",
            target_id=report_id,
            payload={
                "actor": actor_username,
                "role": actor_role,
                "total_signoffs": len(updated.get("sign_offs", [])),
            },
        )

        return updated

    @staticmethod
    def finalise(
        report_id: str,
        actor_user_id: str,
        actor_username: str,
        actor_role: str,
    ) -> dict:
        """
        Finalise a report.

        Requires:
        - Actor is senior_reviewer or lab_director
        - Report is in pending_sign_off status
        - All preflight checks pass
        - At least 2 sign-offs recorded
        """
        db = mongo_client.db

        if actor_role not in ROLES_CAN_FINALISE:
            raise ReportError(
                "Only a senior reviewer or lab director can finalise a report."
            )

        report = db.reports.find_one({"report_id": report_id})
        if not report:
            raise ReportError("Report not found.")

        if report["status"] != "pending_sign_off":
            raise ReportError(
                f"Report must be in 'pending_sign_off' status to finalise. "
                f"Current status: '{report['status']}'."
            )

        sign_offs = report.get("sign_offs", [])
        if len(sign_offs) < 2:
            raise ReportError(
                f"Two sign-offs required before finalisation. "
                f"Only {len(sign_offs)} recorded."
            )

        sample_assay_id = report["sample_assay_id"]
        checks = PreflightService.run_checks(sample_assay_id)
        if not PreflightService.all_passed(checks):
            failed = [c for c in checks if c["status"] == "fail"]
            details = "; ".join(f"{c['check_id']}: {c['detail']}" for c in failed)
            raise ReportError(f"Preflight checks failed — {details}")

        now = datetime.utcnow().isoformat() + "Z"

        # Freeze the snapshot at finalisation time
        updated = db.reports.find_one_and_update(
            {"report_id": report_id},
            {
                "$set": {
                    "status": "finalised",
                    "preflight_checks": checks,
                    "finalised_at": now,
                    "finalised_by": actor_user_id,
                }
            },
            return_document=ReturnDocument.AFTER,
            projection={"_id": 0, "snapshot": 0},
        )

        db.sample_assays.update_one(
            {"sample_assay_id": sample_assay_id},
            {"$set": {"status": "finalised"}},
        )

        AuditService.log(
            event_type="report_finalised",
            target_collection="reports",
            target_id=report_id,
            payload={"actor": actor_username, "role": actor_role, "sample_assay_id": sample_assay_id},
        )

        return updated

    @staticmethod
    def export_json(report_id: str) -> dict:
        """
        Export report as clean JSON (schema v1).
        Only includes reportable (concordant/resolved, non-artifact) variants.
        """
        db = mongo_client.db
        report = db.reports.find_one({"report_id": report_id}, {"_id": 0})
        if not report:
            raise ReportError("Report not found.")

        snapshot = report.get("snapshot", {})

        return {
            "schema_version": report.get("report_schema_version", REPORT_SCHEMA_VERSION),
            "report_id": report["report_id"],
            "report_type": report.get("report_type"),
            "status": report.get("status"),
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "sample": snapshot.get("sample", {}),
            "assay": {
                "assay_id": snapshot.get("assay", {}).get("assay_id"),
                "assay_version": snapshot.get("assay_version"),
            },
            "callset_qc": snapshot.get("callset_qc", {}),
            "variants": {
                "snvs": _reportable_variants(snapshot.get("snvs", [])),
                "cnvs": _reportable_variants(snapshot.get("cnvs", [])),
                "svs": _reportable_variants(snapshot.get("svs", [])),
            },
            "biomarkers": snapshot.get("biomarkers", {}),
            "sign_offs": report.get("sign_offs", []),
            "preflight_checks": report.get("preflight_checks", []),
        }

    @staticmethod
    def create_addendum(
        original_report_id: str,
        created_by_user_id: str,
        created_by_username: str,
    ) -> dict:
        """Create an addendum to a finalised or delivered report."""
        db = mongo_client.db

        original = db.reports.find_one({"report_id": original_report_id})
        if not original:
            raise ReportError("Original report not found.")
        if original["status"] not in ("finalised", "delivered"):
            raise ReportError(
                "Can only create an addendum for a finalised or delivered report."
            )

        report_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat() + "Z"
        sample_assay_id = original["sample_assay_id"]

        doc = {
            "report_id": report_id,
            "sample_assay_id": sample_assay_id,
            "report_schema_version": REPORT_SCHEMA_VERSION,
            "status": "draft",
            "report_type": "addendum",
            "supersedes_report_id": original_report_id,
            "snapshot": _build_snapshot(db, sample_assay_id),
            "preflight_checks": PreflightService.run_checks(sample_assay_id),
            "sign_offs": [],
            "pdf_path": None,
            "json_path": None,
            "delivered_at": None,
            "delivered_to": None,
            "created_at": now,
            "created_by": created_by_user_id,
        }

        db.reports.insert_one(doc)
        doc.pop("_id", None)

        AuditService.log(
            event_type="report_addendum_created",
            target_collection="reports",
            target_id=report_id,
            payload={"original_report_id": original_report_id, "actor": created_by_username},
        )

        return doc
