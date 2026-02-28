from flask import Blueprint, jsonify, request, current_app
from src.extensions import mongo_client
from src.services.samples import SampleService


api_bp = Blueprint("api", __name__)


@api_bp.get("/health")
def health():
    return jsonify({"status": "Omixia running"})


@api_bp.post("/users")
def create_user():
    payload = request.json
    db = mongo_client.db(current_app)

    result = db.users.insert_one({
        "name": payload["name"],
        "email": payload["email"]
    })

    return jsonify({"id": str(result.inserted_id)}), 201


@api_bp.route("/samples")
def list_samples():
    return jsonify(SampleService.list_samples())


@api_bp.route("/samples/<sample_id>")
def get_sample(sample_id):
    return jsonify(SampleService.get_sample(sample_id))


@api_bp.route("/sample-assays/<sample_assay_id>/snvs")
def get_snvs(sample_assay_id):
    return jsonify(SampleService.get_snvs(sample_assay_id))


@api_bp.route("/sample-assays/<sample_assay_id>/summary")
def get_summary(sample_assay_id):
    return jsonify(SampleService.get_summary(sample_assay_id))