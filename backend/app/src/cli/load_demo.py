import json
from flask import current_app
from src.extensions import mongo_client


def load_collection(db, name, path):
    with open(path) as f:
        data = json.load(f)
        if data:
            db[name].delete_many({})
            db[name].insert_many(data)


def load_demo_data(app):
    with app.app_context():
        db = mongo_client.db

        load_collection(db, "samples", "demo_data/samples.json")
        load_collection(db, "sample_assays", "demo_data/sample_assays.json")
        load_collection(db, "callsets", "demo_data/callsets.json")
        load_collection(db, "snvs_raw", "demo_data/snvs_raw.json")
        load_collection(db, "sample_assay_summary", "demo_data/sample_assay_summary.json")

        print("Demo data loaded successfully.")