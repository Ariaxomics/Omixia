from src.extensions import mongo_client
from src.services.samples import REPORTABLE_STATUSES, UNREVIEWED


CHECKS = [
    "all_variants_reviewed",
    "consensus_met",
    "tier_1_2_interpretations_complete",
    "biomarkers_confirmed",
    "qc_passed",
    "no_superseded_callset",
    "two_signoffs_obtained",
]


def _pass(detail: str = "") -> dict:
    return {"status": "pass", "detail": detail}


def _fail(detail: str) -> dict:
    return {"status": "fail", "detail": detail}


class PreflightService:

    @staticmethod
    def run_checks(sample_assay_id: str) -> list[dict]:
        db = mongo_client.db

        assay = db.sample_assays.find_one({"sample_assay_id": sample_assay_id})
        if not assay:
            return [
                {
                    "check_id": "assay_exists",
                    "description": "Sample assay found",
                    **_fail("Sample assay not found."),
                }
            ]

        snvs = list(db.snvs_raw.find({"sample_assay_id": sample_assay_id}))
        cnvs = list(db.cnvs_raw.find({"sample_assay_id": sample_assay_id}))
        svs = list(db.svs_raw.find({"sample_assay_id": sample_assay_id}))
        all_variants = snvs + cnvs + svs

        callset_id = assay.get("active_callset_id")
        callset = db.callsets.find_one({"callset_id": callset_id}) if callset_id else None
        report = db.reports.find_one(
            {"sample_assay_id": sample_assay_id, "status": {"$in": ["draft", "pending_sign_off"]}}
        )

        results = []

        # 1. All variants reviewed — no unreviewed status in review_current
        def is_unreviewed(v):
            rc = v.get("review_current") or {}
            return rc.get("consensus_status", UNREVIEWED) == UNREVIEWED

        unreviewed = [v for v in all_variants if is_unreviewed(v)]
        if unreviewed:
            genes = ", ".join(
                v.get("gene") or v.get("gene_5prime", "?") for v in unreviewed[:5]
            )
            results.append({
                "check_id": "all_variants_reviewed",
                "description": "All variants have been reviewed",
                **_fail(f"{len(unreviewed)} variant(s) still unreviewed: {genes}"),
            })
        else:
            results.append({
                "check_id": "all_variants_reviewed",
                "description": "All variants have been reviewed",
                **_pass(),
            })

        # 2. Consensus met — no discordant or pending variants
        def is_not_reportable(v):
            rc = v.get("review_current") or {}
            cs = rc.get("consensus_status", UNREVIEWED)
            return cs not in REPORTABLE_STATUSES and cs != UNREVIEWED and not rc.get("is_artifact")

        non_reportable = [v for v in all_variants if is_not_reportable(v)]
        if non_reportable:
            results.append({
                "check_id": "consensus_met",
                "description": "All reviewed variants have reached consensus",
                **_fail(
                    f"{len(non_reportable)} variant(s) pending second review or discordant."
                ),
            })
        else:
            results.append({
                "check_id": "consensus_met",
                "description": "All reviewed variants have reached consensus",
                **_pass(),
            })

        # 3. Tier 1/2 interpretations — no blank interpretation on reportable Tier 1/2
        def missing_interpretation(v):
            rc = v.get("review_current") or {}
            tier = rc.get("tier")
            interp = (rc.get("interpretation") or "").strip()
            cs = rc.get("consensus_status", UNREVIEWED)
            return tier in ("tier_1", "tier_2") and cs in REPORTABLE_STATUSES and not interp

        missing = [v for v in all_variants if missing_interpretation(v)]
        if missing:
            genes = ", ".join(
                v.get("gene") or v.get("gene_5prime", "?") for v in missing[:5]
            )
            results.append({
                "check_id": "tier_1_2_interpretations_complete",
                "description": "Tier 1 and 2 variants have interpretation text",
                **_fail(f"{len(missing)} Tier 1/2 variant(s) missing interpretation: {genes}"),
            })
        else:
            results.append({
                "check_id": "tier_1_2_interpretations_complete",
                "description": "Tier 1 and 2 variants have interpretation text",
                **_pass(),
            })

        # 4. Biomarkers confirmed
        biomarker = db.biomarkers.find_one({"sample_assay_id": sample_assay_id})
        if biomarker:
            if biomarker.get("review_status") != "confirmed":
                results.append({
                    "check_id": "biomarkers_confirmed",
                    "description": "MSI/TMB biomarkers reviewed and confirmed",
                    **_fail("Biomarkers have not been confirmed by a reviewer."),
                })
            else:
                results.append({
                    "check_id": "biomarkers_confirmed",
                    "description": "MSI/TMB biomarkers reviewed and confirmed",
                    **_pass(),
                })
        else:
            results.append({
                "check_id": "biomarkers_confirmed",
                "description": "MSI/TMB biomarkers reviewed and confirmed",
                **_pass("No biomarkers present for this assay."),
            })

        # 5. QC passed
        if callset:
            qc_status = callset.get("qc_status", "unknown")
            if qc_status == "passed":
                results.append({
                    "check_id": "qc_passed",
                    "description": "Callset QC within acceptable thresholds",
                    **_pass(),
                })
            else:
                results.append({
                    "check_id": "qc_passed",
                    "description": "Callset QC within acceptable thresholds",
                    **_fail(f"Callset QC status is '{qc_status}'."),
                })
        else:
            results.append({
                "check_id": "qc_passed",
                "description": "Callset QC within acceptable thresholds",
                **_pass("No callset QC record — skipped."),
            })

        # 6. No superseded callset pending
        superseded_count = db.sample_assays.count_documents(
            {"sample_id": assay.get("sample_id"), "status": "superseded"}
        )
        newer_count = db.callsets.count_documents(
            {
                "sample_assay_id": sample_assay_id,
                "import_status": {"$in": ["pending", "normalising", "annotating"]},
            }
        )
        if newer_count > 0:
            results.append({
                "check_id": "no_superseded_callset",
                "description": "No newer callset import in progress",
                **_fail("A new callset import is in progress for this case."),
            })
        else:
            results.append({
                "check_id": "no_superseded_callset",
                "description": "No newer callset import in progress",
                **_pass(),
            })

        # 7. Two sign-offs
        sign_offs = (report or {}).get("sign_offs", [])
        if len(sign_offs) >= 2:
            results.append({
                "check_id": "two_signoffs_obtained",
                "description": "At least two sign-offs on the report",
                **_pass(f"{len(sign_offs)} sign-off(s) recorded."),
            })
        else:
            results.append({
                "check_id": "two_signoffs_obtained",
                "description": "At least two sign-offs on the report",
                **_fail(
                    f"Only {len(sign_offs)} sign-off(s). Two required before finalisation."
                ),
            })

        return results

    @staticmethod
    def all_passed(checks: list[dict]) -> bool:
        return all(c["status"] == "pass" for c in checks)
