from flask import Blueprint, jsonify, request, current_app
from ...extensions import mongo_client

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