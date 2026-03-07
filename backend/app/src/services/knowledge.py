import re
import uuid
from datetime import datetime

from pymongo import ReturnDocument

from src.extensions import mongo_client
from src.services.audit import AuditService

VARIANT_TYPES = {"snv", "cnv", "sv", "fusion"}
TIERS = {"tier_1", "tier_2", "tier_3", "tier_4"}
DISEASE_GROUPS = {"solid", "haematological", "pan_cancer"}


class KnowledgeError(Exception):
    pass


def _lookup_key(data: dict) -> dict:
    """Build the uniqueness query for a knowledge entry based on its variant type."""
    vtype = data.get("variant_type")
    if vtype == "snv":
        return {
            "variant_type": "snv",
            "gene": data.get("gene"),
            "hgvsp": data.get("hgvsp"),
            "disease_subtype": data.get("disease_subtype"),
        }
    if vtype == "cnv":
        return {
            "variant_type": "cnv",
            "gene": data.get("gene"),
            "event_type": data.get("event_type"),
            "disease_group": data.get("disease_group"),
        }
    # sv / fusion
    return {
        "variant_type": {"$in": ["sv", "fusion"]},
        "gene_5prime": data.get("gene_5prime"),
        "gene_3prime": data.get("gene_3prime"),
        "disease_group": data.get("disease_group"),
    }


class KnowledgeService:

    @staticmethod
    def create_entry(data: dict, actor_user_id: str, actor_username: str) -> dict:
        db = mongo_client.db

        vtype = data.get("variant_type")
        if vtype not in VARIANT_TYPES:
            raise KnowledgeError(f"Invalid variant_type '{vtype}'.")

        tier = data.get("tier")
        if tier not in TIERS:
            raise KnowledgeError(f"Invalid tier '{tier}'.")

        disease_group = data.get("disease_group")
        if disease_group not in DISEASE_GROUPS:
            raise KnowledgeError(f"Invalid disease_group '{disease_group}'.")

        existing = db.variant_knowledge.find_one(_lookup_key(data))
        if existing:
            raise KnowledgeError(
                f"A knowledge entry with this key already exists "
                f"(knowledge_id: {existing['knowledge_id']}). Update the existing entry."
            )

        knowledge_id = str(uuid.uuid4())
        now = datetime.utcnow().isoformat() + "Z"

        doc = {
            "knowledge_id": knowledge_id,
            "variant_type": vtype,
            "gene": data.get("gene"),
            "hgvsp": data.get("hgvsp"),
            "hgvsc": data.get("hgvsc"),
            "consequence": data.get("consequence"),
            "event_type": data.get("event_type"),
            "gene_5prime": data.get("gene_5prime"),
            "gene_3prime": data.get("gene_3prime"),
            "disease_group": disease_group,
            "disease_subtype": data.get("disease_subtype") or None,
            "tier": tier,
            "interpretation": data.get("interpretation", ""),
            "evidence_summary": data.get("evidence_summary", ""),
            "evidence_tags": data.get("evidence_tags", []),
            "external_references": data.get("external_references", []),
            "observation_count": 0,
            "contributing_labs": [],
            "created_by": actor_user_id,
            "created_at": now,
            "version": 1,
            "version_history": [],
            "is_contested": False,
            "harmonisation_note": "",
            "federation_eligible": False,
        }

        db.variant_knowledge.insert_one(doc)
        doc.pop("_id", None)

        AuditService.log(
            event_type="knowledge_created",
            target_collection="variant_knowledge",
            target_id=knowledge_id,
            payload={"gene": doc.get("gene"), "variant_type": vtype, "tier": tier, "actor": actor_username},
        )

        return doc

    @staticmethod
    def update_entry(
        knowledge_id: str,
        data: dict,
        actor_user_id: str,
        actor_username: str,
        change_note: str = "",
    ) -> dict:
        db = mongo_client.db

        entry = db.variant_knowledge.find_one({"knowledge_id": knowledge_id})
        if not entry:
            raise KnowledgeError("Knowledge entry not found.")

        new_tier = data.get("tier", entry["tier"])
        if new_tier not in TIERS:
            raise KnowledgeError(f"Invalid tier '{new_tier}'.")

        now = datetime.utcnow().isoformat() + "Z"

        history_entry = {
            "version": entry["version"],
            "tier": entry["tier"],
            "interpretation": entry["interpretation"],
            "evidence_summary": entry.get("evidence_summary", ""),
            "evidence_tags": entry.get("evidence_tags", []),
            "edited_by": actor_user_id,
            "edited_at": now,
            "change_note": change_note,
        }

        new_obs = entry.get("observation_count", 0)
        updated = db.variant_knowledge.find_one_and_update(
            {"knowledge_id": knowledge_id},
            {
                "$set": {
                    "tier": new_tier,
                    "interpretation": data.get("interpretation", entry["interpretation"]),
                    "evidence_summary": data.get("evidence_summary", entry.get("evidence_summary", "")),
                    "evidence_tags": data.get("evidence_tags", entry.get("evidence_tags", [])),
                    "external_references": data.get("external_references", entry.get("external_references", [])),
                    "disease_subtype": data.get("disease_subtype", entry.get("disease_subtype")),
                    "harmonisation_note": data.get("harmonisation_note", entry.get("harmonisation_note", "")),
                    "federation_eligible": new_obs >= 5,
                    "version": entry["version"] + 1,
                },
                "$push": {"version_history": history_entry},
            },
            return_document=ReturnDocument.AFTER,
            projection={"_id": 0},
        )

        AuditService.log(
            event_type="knowledge_updated",
            target_collection="variant_knowledge",
            target_id=knowledge_id,
            payload={
                "previous_tier": entry["tier"],
                "new_tier": new_tier,
                "version": updated["version"],
                "change_note": change_note,
                "actor": actor_username,
            },
        )

        return updated

    @staticmethod
    def get_entry(knowledge_id: str) -> dict | None:
        db = mongo_client.db
        return db.variant_knowledge.find_one({"knowledge_id": knowledge_id}, {"_id": 0})

    @staticmethod
    def list_entries(
        gene: str = "",
        variant_type: str = "",
        tier: str = "",
        disease_group: str = "",
        disease_subtype: str = "",
        limit: int = 100,
    ) -> list:
        db = mongo_client.db
        query: dict = {}
        if gene:
            query["gene"] = {"$regex": f"^{re.escape(gene)}", "$options": "i"}
        if variant_type:
            query["variant_type"] = variant_type
        if tier:
            query["tier"] = tier
        if disease_group:
            query["disease_group"] = disease_group
        if disease_subtype:
            query["disease_subtype"] = {"$regex": disease_subtype, "$options": "i"}
        return list(
            db.variant_knowledge.find(query, {"_id": 0, "version_history": 0})
            .sort("created_at", -1)
            .limit(limit)
        )

    @staticmethod
    def search(text_query: str, filters: dict | None = None) -> list:
        """
        Full-text search scoped to interpretation and evidence_summary.
        Requires at least 3 words (spec section 14).
        """
        words = text_query.strip().split()
        if len(words) < 3:
            raise KnowledgeError("Search requires at least 3 words.")

        db = mongo_client.db
        query: dict = {"$text": {"$search": text_query}}
        if filters:
            if filters.get("gene"):
                query["gene"] = {"$regex": f"^{re.escape(filters['gene'])}", "$options": "i"}
            if filters.get("tier"):
                query["tier"] = filters["tier"]
            if filters.get("disease_group"):
                query["disease_group"] = filters["disease_group"]

        return list(
            db.variant_knowledge.find(
                query,
                {"_id": 0, "version_history": 0, "score": {"$meta": "textScore"}},
            )
            .sort([("score", {"$meta": "textScore"})])
            .limit(50)
        )

    @staticmethod
    def lookup_for_snv(
        gene: str, hgvsp: str, disease_subtype: str | None = None
    ) -> dict | None:
        """
        Return the best knowledge entry for an SNV.
        Priority: disease_subtype-specific match > null disease_subtype (pan-disease).
        """
        db = mongo_client.db
        base = {"variant_type": "snv", "gene": gene, "hgvsp": hgvsp}
        if disease_subtype:
            entry = db.variant_knowledge.find_one(
                {**base, "disease_subtype": disease_subtype}, {"_id": 0}
            )
            if entry:
                return entry
        return db.variant_knowledge.find_one({**base, "disease_subtype": None}, {"_id": 0})

    @staticmethod
    def lookup_for_cnv(gene: str, event_type: str, disease_group: str) -> dict | None:
        db = mongo_client.db
        return db.variant_knowledge.find_one(
            {"variant_type": "cnv", "gene": gene, "event_type": event_type, "disease_group": disease_group},
            {"_id": 0},
        )

    @staticmethod
    def lookup_for_sv(gene_5prime: str, gene_3prime: str, disease_group: str) -> dict | None:
        db = mongo_client.db
        return db.variant_knowledge.find_one(
            {
                "variant_type": {"$in": ["sv", "fusion"]},
                "gene_5prime": gene_5prime,
                "gene_3prime": gene_3prime,
                "disease_group": disease_group,
            },
            {"_id": 0},
        )

    @staticmethod
    def same_gene_entries(gene: str, disease_group: str | None = None) -> list:
        db = mongo_client.db
        query: dict = {"variant_type": "snv", "gene": gene}
        if disease_group and disease_group != "pan_cancer":
            query["disease_group"] = {"$in": [disease_group, "pan_cancer"]}
        return list(
            db.variant_knowledge.find(query, {"_id": 0, "version_history": 0})
            .sort("tier", 1)
            .limit(20)
        )

    @staticmethod
    def same_codon_entries(gene: str, hgvsp: str) -> list:
        """Return knowledge entries for the same codon (e.g. p.G12D → also shows p.G12V, p.G12C)."""
        match = re.match(r"(p\.[A-Z]+\d+)", hgvsp)
        if not match:
            return []
        codon_prefix = re.escape(match.group(1))
        db = mongo_client.db
        return list(
            db.variant_knowledge.find(
                {"variant_type": "snv", "gene": gene, "hgvsp": {"$regex": f"^{codon_prefix}"}},
                {"_id": 0, "version_history": 0},
            ).limit(10)
        )

    @staticmethod
    def get_evidence_panel(snv: dict, disease_subtype: str | None = None) -> dict:
        """
        Return all evidence panel data for a given SNV.
        Used to populate the Novel Variant Evidence Panel (spec 5.3).
        """
        gene = snv.get("gene", "")
        hgvsp = snv.get("hgvsp", "")

        knowledge_entry = KnowledgeService.lookup_for_snv(gene, hgvsp, disease_subtype)
        same_gene = []
        same_codon = []

        if not knowledge_entry:
            same_gene = KnowledgeService.same_gene_entries(gene)
            same_codon = KnowledgeService.same_codon_entries(gene, hgvsp)
            # Exclude exact match from same_gene (would duplicate)
            same_codon = [e for e in same_codon if e.get("hgvsp") != hgvsp]

        return {
            "knowledge_entry": knowledge_entry,
            "same_gene": same_gene,
            "same_codon": same_codon,
        }

    @staticmethod
    def increment_observation(knowledge_id: str) -> None:
        """Increment observation count and update federation eligibility."""
        db = mongo_client.db
        db.variant_knowledge.update_one(
            {"knowledge_id": knowledge_id},
            [
                {
                    "$set": {
                        "observation_count": {"$add": ["$observation_count", 1]},
                        "federation_eligible": {
                            "$gte": [{"$add": ["$observation_count", 1]}, 5]
                        },
                    }
                }
            ],
        )
