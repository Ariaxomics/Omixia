from datetime import datetime

from src.extensions import mongo_client

ACTIVE_STATUSES = {"pending_qc", "analysis_ready", "review_in_progress", "review_complete", "preflight_failed"}
TERMINAL_STATUSES = {"finalised", "report_delivered"}


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.rstrip("Z"))
    except (ValueError, AttributeError):
        return None


class TATService:

    @staticmethod
    def sla_status(assay: dict) -> str:
        """
        Returns:
          'complete'  — case finalised or delivered
          'on_track'  — >48h until SLA deadline
          'amber'     — within 48h of deadline
          'breached'  — past deadline
          'unknown'   — no SLA date set
        """
        if assay.get("status") in TERMINAL_STATUSES:
            return "complete"

        due = _parse_dt(assay.get("sla_due_at"))
        if not due:
            return "unknown"

        hours_remaining = (due - datetime.utcnow()).total_seconds() / 3600
        if hours_remaining < 0:
            return "breached"
        if hours_remaining <= 48:
            return "amber"
        return "on_track"

    @staticmethod
    def is_stalled(assay: dict) -> bool:
        """True if the case is active but has had no state change for >24h."""
        if assay.get("status") not in ACTIVE_STATUSES:
            return False

        state_history = assay.get("state_history") or []
        if state_history:
            last_ts = state_history[-1].get("timestamp")
        else:
            last_ts = assay.get("created_at")

        last_dt = _parse_dt(last_ts)
        if not last_dt:
            return False

        return (datetime.utcnow() - last_dt).total_seconds() / 3600 > 24

    @staticmethod
    def tat_hours(assay: dict) -> float | None:
        """TAT in hours: created_at → report_delivered or finalised (or now if still active)."""
        start = _parse_dt(assay.get("created_at"))
        if not start:
            return None

        end_ts = next(
            (e.get("timestamp") for e in reversed(assay.get("state_history") or [])
             if e.get("status") in ("report_delivered", "finalised")),
            None,
        )
        end = _parse_dt(end_ts) or datetime.utcnow()
        return round((end - start).total_seconds() / 3600, 1)

    @staticmethod
    def dashboard_stats() -> dict:
        """
        Compute lab director dashboard statistics across all non-superseded cases.
        """
        db = mongo_client.db
        all_assays = list(
            db.sample_assays.find({"status": {"$nin": ["superseded"]}}, {"_id": 0})
        )

        active = [a for a in all_assays if a.get("status") in ACTIVE_STATUSES]
        terminal = [a for a in all_assays if a.get("status") in TERMINAL_STATUSES]

        breached = [a for a in active if TATService.sla_status(a) == "breached"]
        amber = [a for a in active if TATService.sla_status(a) == "amber"]
        stalled = [a for a in active if TATService.is_stalled(a)]

        # % within SLA for terminal cases
        within_sla = 0
        tat_list = []
        for a in terminal:
            tat = TATService.tat_hours(a)
            if tat is not None:
                tat_list.append(tat)
            due = _parse_dt(a.get("sla_due_at"))
            end_ts = next(
                (e.get("timestamp") for e in reversed(a.get("state_history") or [])
                 if e.get("status") in ("report_delivered", "finalised")),
                None,
            )
            end_dt = _parse_dt(end_ts)
            if due and end_dt and end_dt <= due:
                within_sla += 1

        pct_within_sla = round(within_sla / len(terminal) * 100, 1) if terminal else None
        median_tat = sorted(tat_list)[len(tat_list) // 2] if tat_list else None

        # Annotate and sort active cases by urgency
        _priority = {"breached": 0, "amber": 1, "on_track": 2, "unknown": 3}
        annotated = []
        for a in active:
            sla = TATService.sla_status(a)
            annotated.append({
                **a,
                "_sla_status": sla,
                "_is_stalled": TATService.is_stalled(a),
                "_tat_hours": TATService.tat_hours(a),
            })
        annotated.sort(key=lambda x: (_priority.get(x["_sla_status"], 3), x.get("sla_due_at") or ""))

        # Per-assay TAT breakdown
        assay_tat: dict[str, list] = {}
        for a in terminal:
            aid = a.get("assay_id", "unknown")
            tat = TATService.tat_hours(a)
            if tat is not None:
                assay_tat.setdefault(aid, []).append(tat)

        assay_breakdown = [
            {
                "assay_id": aid,
                "count": len(tats),
                "median_tat_hours": round(sorted(tats)[len(tats) // 2], 1),
            }
            for aid, tats in sorted(assay_tat.items())
        ]

        return {
            "total_active": len(active),
            "total_finalised": len(terminal),
            "breached_count": len(breached),
            "amber_count": len(amber),
            "stalled_count": len(stalled),
            "pct_within_sla": pct_within_sla,
            "median_tat_hours": round(median_tat, 1) if median_tat else None,
            "active_cases": annotated,
            "assay_breakdown": assay_breakdown,
        }
