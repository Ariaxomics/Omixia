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
