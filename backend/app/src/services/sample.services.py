from flask import current_app


class SampleService:

    @staticmethod
    def list_samples():
        db = current_app.mongo.db
        return list(db.samples.find({}, {"_id": 0}))

    @staticmethod
    def get_sample(sample_id):
        db = current_app.mongo.db
        return db.samples.find_one({"sample_id": sample_id}, {"_id": 0})

    @staticmethod
    def get_sample_assays(sample_id):
        db = current_app.mongo.db
        return list(
            db.sample_assays.find(
                {"sample_id": sample_id},
                {"_id": 0}
            )
        )