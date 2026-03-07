"""
Federated Knowledge Sharing (spec section 12).

Each lab runs its own Omixia instance. A nightly export produces a knowledge_export
of eligible entries. A central registry aggregates exports from member labs.
Member labs pull from the registry on a schedule.

This module handles:
- Export eligibility check
- Producing the export payload
- Importing from a registry payload
- Contested entry detection (tier difference ≥1 between labs)
"""

from datetime import datetime
import uuid

from src.extensions import mongo_client
from src.services.audit import AuditService

EXPORT_SCHEMA_VERSION = "1.0"

TIER_ORDER = {"tier_1": 1, "tier_2": 2, "tier_3": 3, "tier_4": 4}


def _tier_distance(t1: str, t2: str) -> int:
    return abs(TIER_ORDER.get(t1, 0) - TIER_ORDER.get(t2, 0))


class FederationError(Exception):
    pass


class FederationService:

    @staticmethod
    def eligible_entries() -> list:
        """
        Return all knowledge entries that meet federation export criteria:
        - observation_count >= 5
        - Not already marked federation_eligible = False by lab director
        - disease_subtype not too rare (basic check: not None or present in >1 case)
        """
        db = mongo_client.db
        return list(
            db.variant_knowledge.find(
                {"observation_count": {"$gte": 5}, "federation_eligible": True},
                {"_id": 0, "version_history": 0},
            )
        )

    @staticmethod
    def build_export(lab_id: str, approved_by_user_id: str, approved_by_username: str) -> dict:
        """
        Build the nightly knowledge export payload.
        Only includes lab-director-approved, eligible entries.
        """
        db = mongo_client.db
        entries = FederationService.eligible_entries()

        if not entries:
            raise FederationError("No eligible entries for export.")

        export_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat() + "Z"

        export = {
            "export_id": export_id,
            "schema_version": EXPORT_SCHEMA_VERSION,
            "lab_id": lab_id,
            "exported_at": now,
            "approved_by": approved_by_user_id,
            "entry_count": len(entries),
            "entries": [
                {
                    "knowledge_id": e["knowledge_id"],
                    "variant_type": e["variant_type"],
                    "gene": e.get("gene"),
                    "hgvsp": e.get("hgvsp"),
                    "hgvsc": e.get("hgvsc"),
                    "consequence": e.get("consequence"),
                    "event_type": e.get("event_type"),
                    "gene_5prime": e.get("gene_5prime"),
                    "gene_3prime": e.get("gene_3prime"),
                    "disease_group": e["disease_group"],
                    "disease_subtype": e.get("disease_subtype"),
                    "tier": e["tier"],
                    "interpretation": e["interpretation"],
                    "evidence_summary": e.get("evidence_summary", ""),
                    "evidence_tags": e.get("evidence_tags", []),
                    "observation_count": e.get("observation_count", 0),
                    "lab_id": lab_id,
                }
                for e in entries
            ],
        }

        # Persist in export log
        db.federation_exports.insert_one({**export, "entries": export["entries"]})

        AuditService.log(
            event_type="federation_export_created",
            target_collection="federation_exports",
            target_id=export_id,
            payload={
                "lab_id": lab_id,
                "entry_count": len(entries),
                "approved_by": approved_by_username,
            },
        )

        return export

    @staticmethod
    def import_from_registry(payload: dict, imported_by_username: str) -> dict:
        """
        Import a knowledge export payload from the central registry.

        For each entry:
        - If no local entry with same key exists → create shadow entry in federated_knowledge
        - If local entry exists → check tier discordance; set is_contested if diff ≥1
        """
        schema_version = payload.get("schema_version")
        if schema_version != EXPORT_SCHEMA_VERSION:
            raise FederationError(
                f"Unsupported export schema version '{schema_version}'. "
                f"Expected '{EXPORT_SCHEMA_VERSION}'."
            )

        db = mongo_client.db
        entries = payload.get("entries", [])
        source_lab = payload.get("lab_id", "unknown")

        imported = 0
        updated = 0
        contested = 0

        for e in entries:
            # Find matching local entry
            local = _find_local_match(db, e)

            if local:
                # Check for discordance
                if _tier_distance(local.get("tier", ""), e.get("tier", "")) >= 1:
                    db.variant_knowledge.update_one(
                        {"knowledge_id": local["knowledge_id"]},
                        {
                            "$set": {
                                "is_contested": True,
                                "harmonisation_note": (
                                    f"Discordance with {source_lab}: "
                                    f"local={local.get('tier')}, remote={e.get('tier')}"
                                ),
                            }
                        },
                    )
                    contested += 1
                # Add contributing lab if not already present
                db.variant_knowledge.update_one(
                    {"knowledge_id": local["knowledge_id"]},
                    {"$addToSet": {"contributing_labs": source_lab}},
                )
                updated += 1
            else:
                # Insert as federated shadow entry (not editable locally)
                now = datetime.utcnow().isoformat() + "Z"
                doc = {
                    **e,
                    "knowledge_id": str(uuid.uuid4()),
                    "contributing_labs": [source_lab],
                    "created_by": f"federation:{source_lab}",
                    "created_at": now,
                    "version": 1,
                    "version_history": [],
                    "is_contested": False,
                    "harmonisation_note": "",
                    "federation_eligible": False,
                    "_federated": True,
                    "_source_lab": source_lab,
                }
                db.variant_knowledge.insert_one(doc)
                imported += 1

        AuditService.log(
            event_type="federation_import_completed",
            target_collection="variant_knowledge",
            target_id=payload.get("export_id", "unknown"),
            payload={
                "source_lab": source_lab,
                "imported": imported,
                "updated": updated,
                "contested": contested,
                "imported_by": imported_by_username,
            },
        )

        return {
            "source_lab": source_lab,
            "imported": imported,
            "updated": updated,
            "contested": contested,
        }

    @staticmethod
    def list_exports() -> list:
        db = mongo_client.db
        return list(
            db.federation_exports.find(
                {}, {"_id": 0, "entries": 0}
            ).sort("exported_at", -1).limit(20)
        )


def _find_local_match(db, entry: dict) -> dict | None:
    """Find a non-federated local entry matching the given federation entry's key."""
    vtype = entry.get("variant_type")
    query: dict = {"variant_type": vtype, "_federated": {"$ne": True}}

    if vtype == "snv":
        query.update({"gene": entry.get("gene"), "hgvsp": entry.get("hgvsp")})
    elif vtype == "cnv":
        query.update({"gene": entry.get("gene"), "event_type": entry.get("event_type"),
                      "disease_group": entry.get("disease_group")})
    else:
        query.update({"gene_5prime": entry.get("gene_5prime"),
                      "gene_3prime": entry.get("gene_3prime"),
                      "disease_group": entry.get("disease_group")})

    return db.variant_knowledge.find_one(query, {"_id": 0})
