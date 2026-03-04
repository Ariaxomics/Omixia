from datetime import datetime

from pymongo import ReturnDocument

from src.extensions import mongo_client
from src.services.audit import AuditService

# Consensus states
UNREVIEWED = "unreviewed"
PENDING_SECOND = "pending_second_review"
CONCORDANT = "concordant"
DISCORDANT = "discordant"
ESCALATED = "escalated"
RESOLVED = "resolved"

REPORTABLE_STATUSES = {CONCORDANT, RESOLVED}

# Roles allowed to resolve discordant variants
RESOLVER_ROLES = {"senior_reviewer", "lab_director"}


class ReviewError(Exception):
    """Raised when a review action violates the consensus workflow."""
    pass


def _resolve_state_transition(
    consensus: str,
    history: list,
    actor_user_id: str,
    actor_role: str,
    tier: str | None,
    bypass_justification: str,
) -> tuple[str, str]:
    """Return (action, next_consensus_status) or raise ReviewError."""
    if consensus in REPORTABLE_STATUSES:
        if actor_role not in RESOLVER_ROLES:
            raise ReviewError(
                "This variant is already resolved. Only a senior reviewer or lab director can update it."
            )
        return "resolution_updated", RESOLVED

    if consensus in (DISCORDANT, ESCALATED):
        if actor_role not in RESOLVER_ROLES:
            raise ReviewError(
                "This variant is discordant. Only a senior reviewer or lab director can resolve it."
            )
        return "resolved", RESOLVED

    if consensus == PENDING_SECOND:
        first_reviewer_id = history[0]["actor_user_id"] if history else None
        if actor_role in RESOLVER_ROLES and bypass_justification:
            if not bypass_justification.strip():
                raise ReviewError("Bypass justification cannot be empty.")
            return "bypass_approved", RESOLVED
        if actor_user_id == first_reviewer_id:
            raise ReviewError(
                "You already submitted the first review. A different reviewer must provide the second review."
            )
        first_tier = history[0]["tier"] if history else None
        next_cs = CONCORDANT if tier == first_tier else DISCORDANT
        return "reviewed", next_cs

    if consensus == UNREVIEWED:
        return "reviewed", PENDING_SECOND

    raise ReviewError(f"Unexpected consensus state: {consensus!r}")


def _empty_review_current() -> dict:
    return {
        "status": UNREVIEWED,
        "tier": None,
        "is_artifact": False,
        "interpretation": "",
        "reviewed_by": None,
        "reviewed_at": None,
        "reviewer_role": None,
        "consensus_status": UNREVIEWED,
        "knowledge_entry_id": None,
        "knowledge_snapshot": None,
    }


def _build_history_entry(
    action: str,
    tier: str | None,
    is_artifact: bool,
    interpretation: str,
    actor_user_id: str,
    actor_username: str,
    actor_role: str,
    note: str = "",
    bypass_justification: str = "",
) -> dict:
    return {
        "action": action,
        "tier": tier,
        "is_artifact": is_artifact,
        "interpretation": interpretation,
        "actor_user_id": actor_user_id,
        "actor_username": actor_username,
        "actor_role": actor_role,
        "timestamp": datetime.utcnow().isoformat() + "Z",
        "note": note,
        "bypass_justification": bypass_justification,
    }


class SampleService:

    @staticmethod
    def list_samples():
        db = mongo_client.db
        return list(db.samples.find({}, {"_id": 0}))

    @staticmethod
    def get_sample(sample_id):
        db = mongo_client.db
        return db.samples.find_one({"sample_id": sample_id}, {"_id": 0})

    @staticmethod
    def get_sample_assays(sample_id):
        db = mongo_client.db
        return list(db.sample_assays.find({"sample_id": sample_id}, {"_id": 0}))

    @staticmethod
    def get_snvs(sample_assay_id):
        db = mongo_client.db
        return list(db.snvs_raw.find({"sample_assay_id": sample_assay_id}, {"_id": 0}))

    @staticmethod
    def get_summary(sample_assay_id):
        db = mongo_client.db
        return db.sample_assay_summary.find_one(
            {"sample_assay_id": sample_assay_id}, {"_id": 0}
        )

    @staticmethod
    def get_snv(sample_assay_id, chrom, pos, ref, alt) -> dict | None:
        db = mongo_client.db
        snv = db.snvs_raw.find_one(
            {
                "sample_assay_id": sample_assay_id,
                "chrom": chrom,
                "pos": int(pos),
                "ref": ref,
                "alt": alt,
            },
            {"_id": 0},
        )
        if snv is None:
            return None

        # Migrate legacy flat review field → new schema (graceful backcompat)
        if "review_current" not in snv:
            snv["review_current"] = _empty_review_current()
            snv["review_history"] = []

        return snv

    @staticmethod
    def update_snv_review(
        sample_assay_id: str,
        chrom: str,
        pos: str | int,
        ref: str,
        alt: str,
        tier: str | None,
        is_artifact: bool,
        interpretation: str,
        actor_username: str,
        actor_user_id: str,
        actor_role: str,
        note: str = "",
        bypass_justification: str = "",
    ) -> dict:
        """
        Advance the variant through the two-reviewer consensus state machine.

        Returns the updated SNV dict.
        Raises ReviewError for workflow violations.
        """
        db = mongo_client.db
        pos_int = int(pos)
        variant_filter = {
            "sample_assay_id": sample_assay_id,
            "chrom": chrom,
            "pos": pos_int,
            "ref": ref,
            "alt": alt,
        }

        # Read current state under a document-level read
        snv = db.snvs_raw.find_one(variant_filter, {"_id": 0})
        if snv is None:
            raise ReviewError("Variant not found.")

        history = snv.get("review_history") or []
        current = snv.get("review_current") or _empty_review_current()
        consensus = current.get("consensus_status", UNREVIEWED)
        history_len = len(history)

        # --- Determine next state and validate the action ---
        action, next_consensus = _resolve_state_transition(
            consensus, history, actor_user_id, actor_role, tier, bypass_justification
        )

        # --- Build the new history entry ---
        new_entry = _build_history_entry(
            action=action,
            tier=tier,
            is_artifact=is_artifact,
            interpretation=interpretation,
            actor_user_id=actor_user_id,
            actor_username=actor_username,
            actor_role=actor_role,
            note=note,
            bypass_justification=bypass_justification,
        )

        # --- Determine review status label ---
        if is_artifact:
            review_status = "artifact"
        elif next_consensus in REPORTABLE_STATUSES:
            review_status = "reviewed"
        else:
            review_status = "pending"

        new_current = {
            "status": review_status,
            "tier": tier,
            "is_artifact": is_artifact,
            "interpretation": interpretation,
            "reviewed_by": actor_username,
            "reviewed_at": datetime.utcnow().isoformat() + "Z",
            "reviewer_role": actor_role,
            "consensus_status": next_consensus,
            "knowledge_entry_id": current.get("knowledge_entry_id"),
            "knowledge_snapshot": current.get("knowledge_snapshot"),
        }

        # --- Optimistic lock: only write if history length hasn't changed ---
        updated = db.snvs_raw.find_one_and_update(
            {
                **variant_filter,
                "$expr": {
                    "$eq": [
                        {"$size": {"$ifNull": ["$review_history", []]}},
                        history_len,
                    ]
                },
            },
            {
                "$set": {"review_current": new_current},
                "$push": {"review_history": new_entry},
            },
            return_document=ReturnDocument.AFTER,
            projection={"_id": 0},
        )

        if updated is None:
            raise ReviewError(
                "Review was modified by another user at the same time. Please refresh and try again."
            )

        AuditService.log(
            event_type=f"snv_{action}",
            target_collection="snvs_raw",
            target_id=f"{sample_assay_id}:{chrom}:{pos_int}:{ref}:{alt}",
            payload={
                "action": action,
                "tier": tier,
                "is_artifact": is_artifact,
                "consensus_status": next_consensus,
                "actor_username": actor_username,
                "actor_role": actor_role,
                "bypass_justification": bypass_justification,
            },
        )

        SampleService.recalculate_summary(sample_assay_id)
        return updated

    @staticmethod
    def recalculate_summary(sample_assay_id: str) -> None:
        db = mongo_client.db
        snvs = list(db.snvs_raw.find({"sample_assay_id": sample_assay_id}))
        total = len(snvs)

        def rc(s):
            return s.get("review_current") or {}

        reportable = sum(1 for s in snvs if rc(s).get("consensus_status") in REPORTABLE_STATUSES)
        artifacts = sum(1 for s in snvs if rc(s).get("is_artifact") is True)
        unreviewed = sum(1 for s in snvs if rc(s).get("consensus_status", UNREVIEWED) == UNREVIEWED)
        pending = sum(1 for s in snvs if rc(s).get("consensus_status") == PENDING_SECOND)
        discordant = sum(
            1 for s in snvs if rc(s).get("consensus_status") in {DISCORDANT, ESCALATED}
        )

        tier_counts = {}
        for tier_name in ["tier_1", "tier_2", "tier_3", "tier_4"]:
            tier_counts[tier_name] = sum(
                1
                for s in snvs
                if rc(s).get("tier") == tier_name
                and rc(s).get("consensus_status") in REPORTABLE_STATUSES
            )

        cnv_total = db.cnvs_raw.count_documents({"sample_assay_id": sample_assay_id})
        sv_total = db.svs_raw.count_documents({"sample_assay_id": sample_assay_id})

        db.sample_assay_summary.update_one(
            {"sample_assay_id": sample_assay_id},
            {
                "$set": {
                    "raw_counts.snv": total,
                    "raw_counts.cnv": cnv_total,
                    "raw_counts.sv": sv_total,
                    "review_counts.reportable": reportable,
                    "review_counts.artifact": artifacts,
                    "review_counts.unreviewed": unreviewed,
                    "review_counts.pending_second_review": pending,
                    "review_counts.discordant": discordant,
                    "tier_counts": tier_counts,
                }
            },
            upsert=True,
        )

    # ------------------------------------------------------------------
    # CNV methods (Task 6)
    # ------------------------------------------------------------------

    @staticmethod
    def get_cnvs(sample_assay_id: str) -> list:
        db = mongo_client.db
        return list(db.cnvs_raw.find({"sample_assay_id": sample_assay_id}, {"_id": 0}))

    @staticmethod
    def get_cnv(sample_assay_id: str, gene: str) -> dict | None:
        db = mongo_client.db
        cnv = db.cnvs_raw.find_one(
            {"sample_assay_id": sample_assay_id, "gene": gene}, {"_id": 0}
        )
        if cnv is None:
            return None
        if "review_current" not in cnv:
            cnv["review_current"] = _empty_review_current()
            cnv["review_history"] = []
        return cnv

    @staticmethod
    def update_cnv_review(
        sample_assay_id: str,
        gene: str,
        tier: str | None,
        is_artifact: bool,
        interpretation: str,
        actor_username: str,
        actor_user_id: str,
        actor_role: str,
        note: str = "",
        bypass_justification: str = "",
    ) -> dict:
        db = mongo_client.db
        variant_filter = {"sample_assay_id": sample_assay_id, "gene": gene}

        cnv = db.cnvs_raw.find_one(variant_filter, {"_id": 0})
        if cnv is None:
            raise ReviewError("CNV not found.")

        history = cnv.get("review_history") or []
        current = cnv.get("review_current") or _empty_review_current()
        consensus = current.get("consensus_status", UNREVIEWED)
        history_len = len(history)

        # Borderline CNVs require explicit justification in the note
        if cnv.get("is_borderline") and not note.strip():
            raise ReviewError(
                "This CNV is borderline — a justification note is required explaining your classification choice."
            )

        action, next_consensus = _resolve_state_transition(
            consensus, history, actor_user_id, actor_role, tier, bypass_justification
        )

        new_entry = _build_history_entry(
            action=action,
            tier=tier,
            is_artifact=is_artifact,
            interpretation=interpretation,
            actor_user_id=actor_user_id,
            actor_username=actor_username,
            actor_role=actor_role,
            note=note,
            bypass_justification=bypass_justification,
        )

        review_status = "artifact" if is_artifact else ("reviewed" if next_consensus in REPORTABLE_STATUSES else "pending")

        new_current = {
            "status": review_status,
            "tier": tier,
            "is_artifact": is_artifact,
            "interpretation": interpretation,
            "reviewed_by": actor_username,
            "reviewed_at": datetime.utcnow().isoformat() + "Z",
            "reviewer_role": actor_role,
            "consensus_status": next_consensus,
            "knowledge_entry_id": current.get("knowledge_entry_id"),
        }

        updated = db.cnvs_raw.find_one_and_update(
            {
                **variant_filter,
                "$expr": {"$eq": [{"$size": {"$ifNull": ["$review_history", []]}}, history_len]},
            },
            {"$set": {"review_current": new_current}, "$push": {"review_history": new_entry}},
            return_document=ReturnDocument.AFTER,
            projection={"_id": 0},
        )

        if updated is None:
            raise ReviewError("Review was modified concurrently. Please refresh and retry.")

        AuditService.log(
            event_type=f"cnv_{action}",
            target_collection="cnvs_raw",
            target_id=f"{sample_assay_id}:{gene}",
            payload={"action": action, "tier": tier, "consensus_status": next_consensus, "actor_username": actor_username},
        )
        SampleService.recalculate_summary(sample_assay_id)
        return updated

    # ------------------------------------------------------------------
    # SV / Fusion methods (Task 7)
    # ------------------------------------------------------------------

    @staticmethod
    def get_svs(sample_assay_id: str) -> list:
        db = mongo_client.db
        return list(db.svs_raw.find({"sample_assay_id": sample_assay_id}, {"_id": 0}))

    @staticmethod
    def get_sv(sample_assay_id: str, sv_id: str) -> dict | None:
        db = mongo_client.db
        sv = db.svs_raw.find_one(
            {"sample_assay_id": sample_assay_id, "sv_id": sv_id}, {"_id": 0}
        )
        if sv is None:
            return None
        if "review_current" not in sv:
            sv["review_current"] = _empty_review_current()
            sv["review_history"] = []
        return sv

    @staticmethod
    def update_sv_review(
        sample_assay_id: str,
        sv_id: str,
        tier: str | None,
        is_artifact: bool,
        interpretation: str,
        actor_username: str,
        actor_user_id: str,
        actor_role: str,
        note: str = "",
        bypass_justification: str = "",
    ) -> dict:
        db = mongo_client.db
        variant_filter = {"sample_assay_id": sample_assay_id, "sv_id": sv_id}

        sv = db.svs_raw.find_one(variant_filter, {"_id": 0})
        if sv is None:
            raise ReviewError("SV not found.")

        history = sv.get("review_history") or []
        current = sv.get("review_current") or _empty_review_current()
        consensus = current.get("consensus_status", UNREVIEWED)
        history_len = len(history)

        # Novel breakpoints require a note
        if sv.get("is_novel_breakpoint") and not note.strip():
            raise ReviewError(
                "This fusion has a novel breakpoint — a note is required describing your assessment."
            )

        action, next_consensus = _resolve_state_transition(
            consensus, history, actor_user_id, actor_role, tier, bypass_justification
        )

        new_entry = _build_history_entry(
            action=action,
            tier=tier,
            is_artifact=is_artifact,
            interpretation=interpretation,
            actor_user_id=actor_user_id,
            actor_username=actor_username,
            actor_role=actor_role,
            note=note,
            bypass_justification=bypass_justification,
        )

        review_status = "artifact" if is_artifact else ("reviewed" if next_consensus in REPORTABLE_STATUSES else "pending")

        new_current = {
            "status": review_status,
            "tier": tier,
            "is_artifact": is_artifact,
            "interpretation": interpretation,
            "reviewed_by": actor_username,
            "reviewed_at": datetime.utcnow().isoformat() + "Z",
            "reviewer_role": actor_role,
            "consensus_status": next_consensus,
            "knowledge_entry_id": current.get("knowledge_entry_id"),
        }

        updated = db.svs_raw.find_one_and_update(
            {
                **variant_filter,
                "$expr": {"$eq": [{"$size": {"$ifNull": ["$review_history", []]}}, history_len]},
            },
            {"$set": {"review_current": new_current}, "$push": {"review_history": new_entry}},
            return_document=ReturnDocument.AFTER,
            projection={"_id": 0},
        )

        if updated is None:
            raise ReviewError("Review was modified concurrently. Please refresh and retry.")

        AuditService.log(
            event_type=f"sv_{action}",
            target_collection="svs_raw",
            target_id=f"{sample_assay_id}:{sv_id}",
            payload={"action": action, "tier": tier, "consensus_status": next_consensus, "actor_username": actor_username},
        )
        SampleService.recalculate_summary(sample_assay_id)
        return updated

    # ------------------------------------------------------------------
    # Case assignment (Task 5)
    # ------------------------------------------------------------------

    @staticmethod
    def assign_case(
        sample_assay_id: str,
        reviewer_user_ids: list[str],
        bioinformatician_user_id: str | None,
    ) -> dict | None:
        db = mongo_client.db
        result = db.sample_assays.find_one_and_update(
            {"sample_assay_id": sample_assay_id},
            {
                "$set": {
                    "assigned_reviewers": reviewer_user_ids,
                    "assigned_bioinformatician": bioinformatician_user_id,
                }
            },
            return_document=ReturnDocument.AFTER,
            projection={"_id": 0},
        )
        return result
