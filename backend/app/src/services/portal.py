import secrets
import uuid
from datetime import datetime, timedelta

from src.extensions import mongo_client
from src.services.audit import AuditService

TOKEN_TTL_DAYS = 30


class PortalError(Exception):
    pass


class PortalService:

    @staticmethod
    def issue_token(
        report_id: str,
        issued_by_user_id: str,
        issued_by_username: str,
    ) -> dict:
        """
        Generate a new access token for an ordering physician to view a specific report.
        The report must be finalised or delivered.
        """
        db = mongo_client.db

        report = db.reports.find_one({"report_id": report_id})
        if not report:
            raise PortalError("Report not found.")
        if report.get("status") not in ("finalised", "delivered"):
            raise PortalError("Tokens can only be issued for finalised or delivered reports.")

        # Revoke any previous active tokens for this report
        db.report_access_tokens.update_many(
            {"report_id": report_id, "is_revoked": False},
            {"$set": {"is_revoked": True}},
        )

        token = secrets.token_urlsafe(32)
        now = datetime.utcnow()
        doc = {
            "token_id": str(uuid.uuid4()),
            "token": token,
            "report_id": report_id,
            "sample_assay_id": report.get("sample_assay_id"),
            "issued_by": issued_by_user_id,
            "created_at": now.isoformat() + "Z",
            "expires_at": (now + timedelta(days=TOKEN_TTL_DAYS)).isoformat() + "Z",
            "last_accessed_at": None,
            "is_revoked": False,
        }

        db.report_access_tokens.insert_one(doc)
        doc.pop("_id", None)

        AuditService.log(
            event_type="portal_token_issued",
            target_collection="report_access_tokens",
            target_id=doc["token_id"],
            payload={"report_id": report_id, "issued_by": issued_by_username},
        )

        return doc

    @staticmethod
    def validate_token(token: str) -> dict | None:
        """
        Return the token doc if valid (not revoked, not expired).
        Records last access time.
        """
        db = mongo_client.db
        doc = db.report_access_tokens.find_one({"token": token, "is_revoked": False})
        if not doc:
            return None

        expires_at = doc.get("expires_at", "")
        try:
            if datetime.fromisoformat(expires_at.rstrip("Z")) < datetime.utcnow():
                return None
        except (ValueError, AttributeError):
            return None

        db.report_access_tokens.update_one(
            {"token": token},
            {"$set": {"last_accessed_at": datetime.utcnow().isoformat() + "Z"}},
        )
        doc.pop("_id", None)
        return doc

    @staticmethod
    def revoke_token(token_id: str, revoked_by_username: str) -> None:
        db = mongo_client.db
        db.report_access_tokens.update_one(
            {"token_id": token_id},
            {"$set": {"is_revoked": True}},
        )
        AuditService.log(
            event_type="portal_token_revoked",
            target_collection="report_access_tokens",
            target_id=token_id,
            payload={"revoked_by": revoked_by_username},
        )

    @staticmethod
    def get_tokens_for_report(report_id: str) -> list:
        db = mongo_client.db
        return list(
            db.report_access_tokens.find(
                {"report_id": report_id}, {"_id": 0, "token": 0}  # never expose raw token in list
            ).sort("created_at", -1)
        )
