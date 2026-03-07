from flask import Flask
from ..extensions import mongo_client


def ensure_indexes(app: Flask) -> None:
    db = mongo_client.db

    # Users
    db.users.create_index("email", unique=True)
    db.users.create_index("username", unique=True)

    # Assay configs
    db.assay_configs.create_index([("assay_id", 1), ("version", 1)], unique=True)
    db.assay_configs.create_index("is_active")

    # Audit log (write-heavy — no unique constraints)
    db.audit_log.create_index("timestamp")
    db.audit_log.create_index("actor_user_id")
    db.audit_log.create_index("target_id")

    # CNVs
    db.cnvs_raw.create_index([("sample_assay_id", 1), ("gene", 1)], unique=True)

    # SVs
    db.svs_raw.create_index("sample_assay_id")
    db.svs_raw.create_index([("sample_assay_id", 1), ("sv_id", 1)], unique=True)

    # Sample assays
    db.sample_assays.create_index("sample_id")
    db.sample_assays.create_index("status")

    # Biomarkers
    db.biomarkers.create_index("sample_assay_id", unique=True)

    # Callsets
    db.callsets.create_index("callset_id", unique=True)
    db.callsets.create_index("sample_assay_id")
    db.callsets.create_index("vcf_checksum")
    db.callsets.create_index([("sample_assay_id", 1), ("import_status", 1)])

    # Reports
    db.reports.create_index("report_id", unique=True)
    db.reports.create_index("sample_assay_id")
    db.reports.create_index([("sample_assay_id", 1), ("status", 1)])

    # Variant Knowledge
    db.variant_knowledge.create_index("knowledge_id", unique=True)
    db.variant_knowledge.create_index([("variant_type", 1), ("gene", 1)])
    db.variant_knowledge.create_index([("variant_type", 1), ("gene", 1), ("hgvsp", 1), ("disease_subtype", 1)])
    db.variant_knowledge.create_index([("variant_type", 1), ("gene_5prime", 1), ("gene_3prime", 1)])
    # Text index for full-text search on interpretation and evidence_summary
    db.variant_knowledge.create_index(
        [("interpretation", "text"), ("evidence_summary", "text")],
        name="knowledge_text_search",
    )

    # Report access tokens (physician portal)
    db.report_access_tokens.create_index("token", unique=True)
    db.report_access_tokens.create_index("report_id")
    db.report_access_tokens.create_index([("report_id", 1), ("revoked", 1)])

    # Federation exports
    db.federation_exports.create_index("export_id", unique=True)
    db.federation_exports.create_index("target_lab_id")
    db.federation_exports.create_index("exported_at")
