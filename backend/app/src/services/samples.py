from flask import current_app
from src.extensions import mongo_client


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
        return list(
            db.sample_assays.find(
                {"sample_id": sample_id},
                {"_id": 0}
            )
        )
    
    @staticmethod
    def get_snvs(sample_assay_id):
        db = mongo_client.db
        return list(
            db.snvs_raw.find(
                {"sample_assay_id": sample_assay_id},
                {"_id": 0}
            )
        )

    @staticmethod
    def get_summary(sample_assay_id):
        db = mongo_client.db
        return db.sample_assay_summary.find_one(
            {"sample_assay_id": sample_assay_id},
            {"_id": 0}
        )