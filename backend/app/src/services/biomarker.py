from datetime import datetime

from src.extensions import mongo_client
from src.services.audit import AuditService


# Discordant combinations that require explicit acknowledgement
_DISCORDANT_COMBINATIONS = {
    ("MSI-H", "TMB-Low"),
    ("MSS", "TMB-High"),
}

_DISCORDANCE_NOTES = {
    ("MSI-H", "TMB-Low"): (
        "MSI-H with TMB-Low detected. MSI and TMB measure different aspects of genomic "
        "instability using independent algorithms. MSI reflects instability at microsatellite "
        "loci; TMB reflects total somatic mutation burden per megabase. Divergence is "
        "biologically possible and does not indicate an error. Both values should be reported "
        "with this explanatory note."
    ),
    ("MSS", "TMB-High"): (
        "MSS with TMB-High detected. High mutation burden without microsatellite instability "
        "can occur in tumours with POLE/POLD1 mutations or other mutational signatures. "
        "Both values should be reported with clinical context."
    ),
}


class BiomarkerError(Exception):
    pass


def _get_active_tmb_threshold(tmb_thresholds: list) -> dict | None:
    """Return the most recently effective TMB threshold as of now."""
    if not tmb_thresholds:
        return None
    now = datetime.utcnow().isoformat() + "Z"
    active = [t for t in tmb_thresholds if t.get("effective_from", "") <= now]
    if not active:
        return tmb_thresholds[0]
    return sorted(active, key=lambda t: t["effective_from"], reverse=True)[0]


def _classify(
    msi_score: float,
    tmb_mut_per_mb: float,
    msi_thresholds: dict,
    tmb_thresholds: list,
) -> tuple[str, str, str, bool, str, dict]:
    """
    Returns:
        msi_classification, tmb_classification,
        msi_threshold_snapshot, tmb_threshold_snapshot,
        discordance_flag, discordance_note
    """
    # MSI classification
    msi_high = msi_thresholds.get("msi_high", 3.5)
    msi_low = msi_thresholds.get("msi_low", 1.5)
    if msi_score >= msi_high:
        msi_class = "MSI-H"
    elif msi_score >= msi_low:
        msi_class = "MSI-L"
    else:
        msi_class = "MSS"

    # TMB classification
    tmb_threshold = _get_active_tmb_threshold(tmb_thresholds)
    tmb_cutoff = (tmb_threshold or {}).get("min_mut_per_mb", 10)
    tmb_class = "TMB-High" if tmb_mut_per_mb >= tmb_cutoff else "TMB-Low"

    # Discordance check
    combo = (msi_class, tmb_class)
    discordant = combo in _DISCORDANT_COMBINATIONS
    disc_note = _DISCORDANCE_NOTES.get(combo, "") if discordant else ""

    return (
        msi_class,
        tmb_class,
        {"msi_high": msi_high, "msi_low": msi_low},
        tmb_threshold or {},
        discordant,
        disc_note,
    )


class BiomarkerService:

    @staticmethod
    def get_biomarkers(sample_assay_id: str) -> dict | None:
        db = mongo_client.db
        return db.biomarkers.find_one({"sample_assay_id": sample_assay_id}, {"_id": 0})

    @staticmethod
    def classify_from_callset(sample_assay_id: str) -> dict:
        """
        Read raw MSI/TMB scores from the active callset, classify them using
        the assay config thresholds, and upsert a biomarker document.
        Returns the upserted document.
        """
        db = mongo_client.db

        assay = db.sample_assays.find_one({"sample_assay_id": sample_assay_id})
        if not assay:
            raise BiomarkerError("Sample assay not found.")

        callset_id = assay.get("active_callset_id")
        callset = db.callsets.find_one({"callset_id": callset_id}) if callset_id else None
        if not callset:
            raise BiomarkerError("Active callset not found.")

        qc = callset.get("qc_metrics", {})
        msi_score = qc.get("msi_score")
        tmb_mut_per_mb = qc.get("tmb_mut_per_mb")

        if msi_score is None or tmb_mut_per_mb is None:
            raise BiomarkerError("MSI score or TMB value missing from callset QC metrics.")

        config = db.assay_configs.find_one(
            {"assay_id": assay.get("assay_id"), "is_active": True}
        )
        if not config:
            raise BiomarkerError("Assay config not found.")

        (
            msi_class, tmb_class,
            msi_thresh_snap, tmb_thresh_snap,
            discordant, disc_note,
        ) = _classify(
            msi_score,
            tmb_mut_per_mb,
            config.get("msi_thresholds", {}),
            config.get("tmb_thresholds", []),
        )

        doc = {
            "sample_assay_id": sample_assay_id,
            "callset_id": callset_id,
            "msi_score": msi_score,
            "msi_classification": msi_class,
            "msi_threshold_version": msi_thresh_snap,
            "tmb_mut_per_mb": tmb_mut_per_mb,
            "tmb_classification": tmb_class,
            "tmb_threshold_version": tmb_thresh_snap,
            "discordance_flag": discordant,
            "discordance_note": disc_note,
            "review_status": "unreviewed",
            "reviewed_by": None,
            "reviewed_by_id": None,
            "reviewed_at": None,
            "reviewer_note": "",
            "discordance_acknowledged": False,
            "classified_at": datetime.utcnow().isoformat() + "Z",
        }

        db.biomarkers.replace_one(
            {"sample_assay_id": sample_assay_id},
            doc,
            upsert=True,
        )
        doc.pop("_id", None)
        return doc

    @staticmethod
    def confirm(
        sample_assay_id: str,
        reviewer_note: str,
        discordance_acknowledged: bool,
        actor_username: str,
        actor_user_id: str,
        actor_role: str,
    ) -> dict:
        """
        Confirm biomarker values for reporting.
        If discordance_flag is True, discordance_acknowledged must be True.
        """
        db = mongo_client.db
        biomarker = db.biomarkers.find_one({"sample_assay_id": sample_assay_id})
        if not biomarker:
            raise BiomarkerError("No biomarker record found for this assay.")

        if biomarker.get("discordance_flag") and not discordance_acknowledged:
            raise BiomarkerError(
                "Discordance between MSI and TMB classifications must be explicitly "
                "acknowledged before confirming."
            )

        now = datetime.utcnow().isoformat() + "Z"
        db.biomarkers.update_one(
            {"sample_assay_id": sample_assay_id},
            {
                "$set": {
                    "review_status": "confirmed",
                    "reviewed_by": actor_username,
                    "reviewed_by_id": actor_user_id,
                    "reviewed_at": now,
                    "reviewer_note": reviewer_note,
                    "discordance_acknowledged": discordance_acknowledged,
                }
            },
        )

        AuditService.log(
            event_type="biomarkers_confirmed",
            target_collection="biomarkers",
            target_id=sample_assay_id,
            payload={
                "msi_classification": biomarker.get("msi_classification"),
                "tmb_classification": biomarker.get("tmb_classification"),
                "discordance_flag": biomarker.get("discordance_flag"),
                "discordance_acknowledged": discordance_acknowledged,
                "actor_username": actor_username,
            },
        )

        return db.biomarkers.find_one(
            {"sample_assay_id": sample_assay_id}, {"_id": 0}
        )

    @staticmethod
    def flag_for_review(sample_assay_id: str) -> dict | None:
        """Reset a confirmed biomarker back to unreviewed (e.g. after callset update)."""
        db = mongo_client.db
        db.biomarkers.update_one(
            {"sample_assay_id": sample_assay_id},
            {
                "$set": {
                    "review_status": "unreviewed",
                    "reviewed_by": None,
                    "reviewed_by_id": None,
                    "reviewed_at": None,
                    "reviewer_note": "",
                    "discordance_acknowledged": False,
                }
            },
        )
        return db.biomarkers.find_one(
            {"sample_assay_id": sample_assay_id}, {"_id": 0}
        )
