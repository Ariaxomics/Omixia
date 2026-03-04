from src.extensions import mongo_client


class AssayConfigService:

    @staticmethod
    def get_config(assay_id: str, version: str) -> dict | None:
        db = mongo_client.db
        return db.assay_configs.find_one(
            {"assay_id": assay_id, "version": version},
            {"_id": 0},
        )

    @staticmethod
    def get_active_config(assay_id: str) -> dict | None:
        db = mongo_client.db
        return db.assay_configs.find_one(
            {"assay_id": assay_id, "is_active": True},
            {"_id": 0},
        )

    @staticmethod
    def list_configs() -> list:
        db = mongo_client.db
        return list(db.assay_configs.find({}, {"_id": 0}))

    @staticmethod
    def create_config(data: dict) -> dict:
        db = mongo_client.db
        db.assay_configs.insert_one(data)
        data.pop("_id", None)
        return data
