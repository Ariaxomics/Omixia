from src.extensions import mongo_client


class GapAnalysisService:

    @staticmethod
    def query_gene_coverage(gene: str, assay_id: str | None = None) -> dict:
        """
        Return all cases where the given gene was NOT covered by the assay panel.
        Informational only — no clinical action from this view.
        """
        db = mongo_client.db

        # Get all assay configs (optionally filter by assay_id)
        config_query: dict = {"is_active": True}
        if assay_id:
            config_query["assay_id"] = assay_id
        configs = list(db.assay_configs.find(config_query, {"_id": 0}))

        # Determine which assay versions cover the gene
        covered_by: list[dict] = []
        not_covered_by: list[dict] = []
        for config in configs:
            panel_genes = [g["gene"] for g in config.get("gene_panel", [])]
            entry = {
                "assay_id": config["assay_id"],
                "version": config.get("version"),
                "panel_size": len(panel_genes),
            }
            if gene.upper() in [g.upper() for g in panel_genes]:
                covered_by.append(entry)
            else:
                not_covered_by.append(entry)

        # Find all cases that used a non-covering assay version
        uncovered_cases = []
        for cfg in not_covered_by:
            cases = list(
                db.sample_assays.find(
                    {"assay_id": cfg["assay_id"], "status": {"$nin": ["superseded"]}},
                    {"_id": 0, "sample_assay_id": 1, "sample_id": 1, "assay_id": 1,
                     "assay_version": 1, "status": 1, "created_at": 1},
                )
            )
            for c in cases:
                c["_gap_reason"] = f"{cfg['assay_id']} v{cfg['version']} does not include {gene}"
            uncovered_cases.extend(cases)

        return {
            "gene": gene,
            "covered_by": covered_by,
            "not_covered_by": not_covered_by,
            "uncovered_cases": uncovered_cases,
            "uncovered_case_count": len(uncovered_cases),
        }

    @staticmethod
    def list_assay_versions() -> list:
        db = mongo_client.db
        return list(db.assay_configs.find({}, {"_id": 0, "assay_id": 1, "version": 1, "gene_panel": 1, "is_active": 1}))


class CohortService:

    @staticmethod
    def query(
        gene: str = "",
        tier: str = "",
        variant_type: str = "",
        assay_id: str = "",
        disease_subtype: str = "",
        acknowledge_multi_version: bool = False,
    ) -> dict:
        """
        Query variants across cases.
        Returns a panel version breakdown warning if multiple assay versions are involved.
        """
        db = mongo_client.db

        # Determine which collections to query
        results: list[dict] = []
        panel_versions: set[str] = set()

        def _build_variant_query() -> dict:
            q: dict = {}
            if gene:
                q["gene"] = {"$regex": f"^{gene}", "$options": "i"}
            return q

        if not variant_type or variant_type == "snv":
            snv_q = _build_variant_query()
            if tier:
                snv_q["review_current.tier"] = tier
            for v in db.snvs_raw.find(snv_q, {"_id": 0, "review_history": 0}):
                v["_variant_type"] = "snv"
                results.append(v)

        if not variant_type or variant_type == "cnv":
            cnv_q = _build_variant_query()
            if tier:
                cnv_q["review_current.tier"] = tier
            for v in db.cnvs_raw.find(cnv_q, {"_id": 0, "review_history": 0}):
                v["_variant_type"] = "cnv"
                results.append(v)

        if not variant_type or variant_type in ("sv", "fusion"):
            sv_q: dict = {}
            if gene:
                sv_q["$or"] = [
                    {"gene_5prime": {"$regex": f"^{gene}", "$options": "i"}},
                    {"gene_3prime": {"$regex": f"^{gene}", "$options": "i"}},
                ]
            if tier:
                sv_q["review_current.tier"] = tier
            for v in db.svs_raw.find(sv_q, {"_id": 0, "review_history": 0}):
                v["_variant_type"] = "sv"
                results.append(v)

        # Collect assay versions used
        assay_ids = {v.get("sample_assay_id") for v in results if v.get("sample_assay_id")}
        if assay_ids:
            assays = list(db.sample_assays.find(
                {"sample_assay_id": {"$in": list(assay_ids)}},
                {"_id": 0, "sample_assay_id": 1, "assay_id": 1, "assay_version": 1},
            ))
            assay_map = {a["sample_assay_id"]: a for a in assays}
            for v in results:
                assay_info = assay_map.get(v.get("sample_assay_id"), {})
                v["_assay_id"] = assay_info.get("assay_id")
                v["_assay_version"] = assay_info.get("assay_version")
                panel_versions.add(f"{assay_info.get('assay_id')} v{assay_info.get('assay_version')}")

        # Filter by assay_id if requested
        if assay_id:
            results = [v for v in results if v.get("_assay_id") == assay_id]
            panel_versions = {p for p in panel_versions if p.startswith(assay_id)}

        multi_version_warning = len(panel_versions) > 1 and not acknowledge_multi_version

        return {
            "results": results if not multi_version_warning else [],
            "total": len(results),
            "panel_versions": sorted(panel_versions),
            "multi_version_warning": multi_version_warning,
            "requires_acknowledgment": multi_version_warning,
        }
