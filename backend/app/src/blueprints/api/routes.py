from flask import Blueprint, jsonify, request, current_app
from ...extensions import mongo_client
from src.services.sample_service import SampleService

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


@api_bp.route("/samples", methods=["GET"])
def list_samples():
    samples = SampleService.list_samples()
    return jsonify(samples)


@api_bp.route("/samples/<sample_id>", methods=["GET"])
def get_sample(sample_id):
    sample = SampleService.get_sample(sample_id)
    return jsonify(sample)


@api_bp.route("/samples/<sample_id>/assays", methods=["GET"])
def get_sample_assays(sample_id):
    assays = SampleService.get_sample_assays(sample_id)
    return jsonify(assays)