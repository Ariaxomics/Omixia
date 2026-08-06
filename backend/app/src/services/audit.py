import sys
import uuid
from datetime import datetime

from src.extensions import mongo_client


class AuditService:
    """Append-only audit log. No updates or deletes are ever performed."""

    @staticmethod
    def log(
        event_type: str,
        target_collection: str,
        target_id: str,
        payload: dict,
        actor_user_id: str | None = None,
        actor_role: str | None = None,
    ) -> None:
        """Append an immutable audit event. Safe to call from any context."""
        try:
            from src.request_context import get_current_request

            user = None
            ip_address = None
            session_id = None

            request = get_current_request()
            if request is not None:
                session = getattr(request.state, "session", None)
                if session is not None:
                    user = session.get("user")
                    session_id = getattr(session, "_session_id", None)
                ip_address = request.client.host if request.client else None

            db = mongo_client.db
            db.audit_log.insert_one(
                {
                    "event_id": str(uuid.uuid4()),
                    "event_type": event_type,
                    "actor_user_id": actor_user_id or (user["user_id"] if user else "system"),
                    "actor_role": actor_role or (user["role"] if user else "system"),
                    "target_collection": target_collection,
                    "target_id": target_id,
                    "payload": payload,
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "ip_address": ip_address,
                    "session_id": session_id,
                }
            )
        except Exception as exc:
            # Audit failure must never break the review workflow
            print(f"[audit] WARNING: failed to write audit log: {exc}", file=sys.stderr)
