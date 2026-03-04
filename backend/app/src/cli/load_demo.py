import json
import uuid
from datetime import datetime

import bcrypt
from flask import current_app
from src.extensions import mongo_client


def load_collection(db, name, path):
    with open(path) as f:
        data = json.load(f)
        if data:
            db[name].delete_many({})
            db[name].insert_many(data)


def load_users(db, path):
    """Load demo users, hashing passwords at load time."""
    with open(path) as f:
        users = json.load(f)

    db.users.delete_many({})
    for u in users:
        password_hash = bcrypt.hashpw(u["password"].encode(), bcrypt.gensalt()).decode()
        db.users.insert_one({
            "user_id": str(uuid.uuid4()),
            "username": u["username"],
            "email": u["email"],
            "role": u["role"],
            "full_name": u["full_name"],
            "password_hash": password_hash,
            "created_at": datetime.utcnow().isoformat() + "Z",
            "is_active": True,
        })
    print(f"  Loaded {len(users)} demo users.")


def load_demo_data(app):
    with app.app_context():
        db = mongo_client.db

        load_collection(db, "samples", "demo_data/samples.json")
        load_collection(db, "sample_assays", "demo_data/sample_assays.json")
        load_collection(db, "callsets", "demo_data/callsets.json")
        load_collection(db, "snvs_raw", "demo_data/snvs_raw.json")
        load_collection(db, "sample_assay_summary", "demo_data/sample_assay_summary.json")
        load_collection(db, "assay_configs", "demo_data/assay_configs.json")
        load_collection(db, "cnvs_raw", "demo_data/cnvs_raw.json")
        load_collection(db, "svs_raw", "demo_data/svs_raw.json")
        load_collection(db, "biomarkers", "demo_data/biomarkers.json")
        load_users(db, "demo_data/users.json")

        print("Demo data loaded successfully.")
        print("")
        print("Demo credentials (password: omixia_demo_1):")
        print("  geneticist  — reviewer")
        print("  senior      — senior_reviewer")
        print("  director    — lab_director")
        print("  bioinf      — bioinformatician")
