import uuid
from datetime import datetime

import bcrypt

from src.extensions import mongo_client

VALID_ROLES = (
    "bioinformatician",
    "reviewer",
    "senior_reviewer",
    "lab_director",
    "ordering_physician",
)


class UserService:

    @staticmethod
    def get_by_username(username: str) -> dict | None:
        db = mongo_client.db
        return db.users.find_one({"username": username}, {"_id": 0})

    @staticmethod
    def get_by_id(user_id: str) -> dict | None:
        db = mongo_client.db
        return db.users.find_one({"user_id": user_id}, {"_id": 0})

    @staticmethod
    def verify_password(plain: str, password_hash: str) -> bool:
        return bcrypt.checkpw(plain.encode(), password_hash.encode())

    @staticmethod
    def authenticate(username: str, password: str) -> dict | None:
        """Return safe user dict (no password_hash) on success, None on failure."""
        db = mongo_client.db
        user = db.users.find_one({"username": username, "is_active": True})
        if not user:
            return None
        if not bcrypt.checkpw(password.encode(), user["password_hash"].encode()):
            return None
        return {
            "user_id": user["user_id"],
            "username": user["username"],
            "email": user["email"],
            "role": user["role"],
            "full_name": user["full_name"],
        }

    @staticmethod
    def create_user(
        username: str,
        email: str,
        role: str,
        full_name: str,
        password: str,
    ) -> dict:
        if role not in VALID_ROLES:
            raise ValueError(f"Invalid role '{role}'. Must be one of: {', '.join(VALID_ROLES)}")

        db = mongo_client.db

        if db.users.find_one({"username": username}):
            raise ValueError(f"Username '{username}' already exists.")

        if db.users.find_one({"email": email}):
            raise ValueError(f"Email '{email}' already exists.")

        password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

        user = {
            "user_id": str(uuid.uuid4()),
            "username": username,
            "email": email,
            "role": role,
            "full_name": full_name,
            "password_hash": password_hash,
            "created_at": datetime.utcnow().isoformat() + "Z",
            "is_active": True,
        }
        db.users.insert_one(user)

        user.pop("_id", None)
        user.pop("password_hash", None)
        return user
