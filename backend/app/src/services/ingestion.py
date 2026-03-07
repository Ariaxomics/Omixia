import hashlib
import json
import os
import re
import subprocess
import uuid
from datetime import datetime

from src.extensions import mongo_client
from src.services.assay_config import AssayConfigService
from src.services.audit import AuditService


class IngestionError(Exception):
    pass


# Default CSQ field order produced by VEP --everything
DEFAULT_CSQ_FIELDS = [
    "Allele", "Consequence", "IMPACT", "SYMBOL", "Gene", "Feature_type",
    "Feature", "BIOTYPE", "EXON", "INTRON", "HGVSc", "HGVSp",
    "cDNA_position", "CDS_position", "Protein_position", "Amino_acids",
    "Codons", "Existing_variation", "DISTANCE", "STRAND", "FLAGS",
    "VARIANT_CLASS", "SYMBOL_SOURCE", "HGNC_ID", "CANONICAL", "MANE_SELECT",
    "MANE_PLUS_CLINICAL", "TSL", "APPRIS", "CCDS", "ENSP", "SWISSPROT",
    "TREMBL", "UNIPARC", "UNIPROT_ISOFORM", "GENE_PHENO", "SIFT", "PolyPhen",
    "DOMAINS", "miRNA", "AF", "AFR_AF", "AMR_AF", "EAS_AF", "EUR_AF",
    "SAS_AF", "gnomADe_AF", "gnomADe_AFR_AF", "gnomADe_AMR_AF",
    "gnomADe_ASJ_AF", "gnomADe_EAS_AF", "gnomADe_FIN_AF", "gnomADe_NFE_AF",
    "gnomADe_OTH_AF", "gnomADe_SAS_AF", "CADD_PHRED", "CADD_RAW",
    "COSMIC", "PUBMED",
]


class IngestionService:

    @staticmethod
    def compute_checksum(path: str) -> str:
        sha = hashlib.sha256()
        with open(path, "rb") as fh:
            for chunk in iter(lambda: fh.read(65536), b""):
                sha.update(chunk)
        return sha.hexdigest()

    @staticmethod
    def already_imported(checksum: str) -> bool:
        db = mongo_client.db
        return db.callsets.find_one(
            {"vcf_checksum": checksum, "import_status": "imported"},
            {"_id": 1},
        ) is not None

    @staticmethod
    def _set_import_status(db, callset_id: str, status: str, error: str = "") -> None:
        update: dict = {"import_status": status}
        if error:
            update["import_error"] = error
        db.callsets.update_one({"callset_id": callset_id}, {"$set": update})

    # ------------------------------------------------------------------
    # External tool wrappers
    # ------------------------------------------------------------------

    @staticmethod
    def run_bcftools_norm(
        vcf_path: str,
        output_path: str,
        ref_fasta: str,
        bcftools_bin: str = "bcftools",
    ) -> None:
        """Left-align + split multiallelics + trim padding via bcftools norm."""
        cmd = [
            bcftools_bin, "norm",
            "-m", "-any",
            "-o", output_path,
            "-O", "z",
        ]
        if ref_fasta:
            cmd += ["-f", ref_fasta]
        cmd.append(vcf_path)
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise IngestionError(f"bcftools norm failed: {result.stderr.strip()}")

    @staticmethod
    def run_vep(
        normalised_vcf: str,
        output_vcf: str,
        vep_bin: str = "vep",
        vep_cache: str = "",
    ) -> str:
        """Run Ensembl VEP annotation. Returns version string."""
        cmd = [
            vep_bin,
            "--input_file", normalised_vcf,
            "--output_file", output_vcf,
            "--format", "vcf",
            "--vcf",
            "--everything",
            "--canonical",
            "--offline",
            "--no_stats",
            "--force_overwrite",
        ]
        if vep_cache:
            cmd += ["--dir_cache", vep_cache]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise IngestionError(f"VEP annotation failed: {result.stderr.strip()}")
        for line in result.stderr.splitlines():
            if "ensembl-vep" in line.lower() or "vep version" in line.lower():
                return line.strip()
        return "unknown"

    # ------------------------------------------------------------------
    # VCF parsing
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_csq_header(vcf_path: str) -> list[str]:
        """Extract CSQ field names from ##INFO=<ID=CSQ…> header line."""
        try:
            with open(vcf_path) as fh:
                for line in fh:
                    if not line.startswith("#"):
                        break
                    if line.startswith("##INFO=<ID=CSQ"):
                        m = re.search(r'Format: ([^"]+)"', line)
                        if m:
                            return m.group(1).split("|")
        except UnicodeDecodeError:
            pass
        return DEFAULT_CSQ_FIELDS

    @staticmethod
    def _sample_gt(fmt: str, sample_col: str) -> tuple[float, int, int]:
        """Return (vaf, depth, allele_count) from FORMAT + sample columns."""
        keys = fmt.split(":")
        vals = sample_col.split(":")
        gt = dict(zip(keys, vals))

        vaf = 0.0
        depth = 0
        allele_count = 0

        if "AF" in gt:
            try:
                vaf = float(gt["AF"].split(",")[0])
            except (ValueError, IndexError):
                pass

        if "AD" in gt:
            try:
                ads = list(map(int, gt["AD"].split(",")))
                depth = sum(ads)
                allele_count = ads[1] if len(ads) > 1 else 0
                if vaf == 0.0 and depth > 0:
                    vaf = allele_count / depth
            except (ValueError, IndexError):
                pass

        if "DP" in gt and depth == 0:
            try:
                depth = int(gt["DP"])
            except ValueError:
                pass

        return vaf, depth, allele_count

    @staticmethod
    def parse_vep_vcf(
        annotated_vcf: str,
        sample_assay_id: str,
        callset_id: str,
    ) -> list[dict]:
        """Parse VEP-annotated VCF into snvs_raw documents."""
        csq_fields = IngestionService._parse_csq_header(annotated_vcf)
        snvs: list[dict] = []

        with open(annotated_vcf) as fh:
            for line in fh:
                if line.startswith("#"):
                    continue
                cols = line.rstrip("\n").split("\t")
                if len(cols) < 8:
                    continue
                chrom = cols[0]
                pos = int(cols[1])
                ref = cols[3]
                alt_field = cols[4]
                info_raw = cols[7]
                fmt = cols[8] if len(cols) > 8 else "GT"
                sample_col = cols[9] if len(cols) > 9 else "."

                vaf, depth, allele_count = IngestionService._sample_gt(fmt, sample_col)

                # Parse INFO
                info_dict: dict[str, str] = {}
                for item in info_raw.split(";"):
                    if "=" in item:
                        k, v = item.split("=", 1)
                        info_dict[k] = v
                    else:
                        info_dict[item] = "1"

                # Choose canonical transcript from CSQ
                best_ann: dict[str, str] = {}
                csq_raw = info_dict.get("CSQ", "")
                if csq_raw:
                    for tx_ann in csq_raw.split(","):
                        parts = tx_ann.split("|")
                        ann = dict(zip(csq_fields, parts))
                        if ann.get("CANONICAL") == "YES":
                            best_ann = ann
                            break
                    if not best_ann:
                        parts = csq_raw.split(",")[0].split("|")
                        best_ann = dict(zip(csq_fields, parts))

                gene = best_ann.get("SYMBOL", "")
                transcript_id = best_ann.get("Feature", "")
                hgvsc_raw = best_ann.get("HGVSc", "")
                hgvsc = hgvsc_raw.split(":")[-1] if ":" in hgvsc_raw else hgvsc_raw
                hgvsp_raw = best_ann.get("HGVSp", "")
                hgvsp = hgvsp_raw.split(":")[-1] if ":" in hgvsp_raw else hgvsp_raw
                consequence = best_ann.get("Consequence", "")
                exon_number = best_ann.get("EXON", "")

                domain = ""
                if best_ann.get("DOMAINS"):
                    domain = best_ann["DOMAINS"].split("&")[0]

                gnomad_af_str = best_ann.get("gnomADe_AF") or best_ann.get("AF") or ""
                try:
                    gnomad_af: float | None = float(gnomad_af_str) if gnomad_af_str else None
                except ValueError:
                    gnomad_af = None

                is_hotspot = bool(best_ann.get("COSMIC"))
                alts = alt_field.split(",")

                snv = {
                    "snv_id": str(uuid.uuid4()),
                    "sample_assay_id": sample_assay_id,
                    "callset_id": callset_id,
                    "chrom": chrom,
                    "pos": pos,
                    "ref": ref,
                    "alt": alts[0],
                    "gene": gene,
                    "transcript_id": transcript_id,
                    "hgvsc": hgvsc,
                    "hgvsp": hgvsp,
                    "consequence": consequence,
                    "exon_number": exon_number,
                    "domain": domain,
                    "vaf": vaf,
                    "depth": depth,
                    "allele_count": allele_count,
                    "ccf": None,
                    "ccf_inputs": None,
                    "annotation_version": "",
                    "is_hotspot": is_hotspot,
                    "gnomad_af": gnomad_af,
                    "review_current": {
                        "status": "unreviewed",
                        "tier": None,
                        "is_artifact": False,
                        "interpretation": "",
                        "reviewed_by": None,
                        "reviewed_at": None,
                        "reviewer_role": None,
                        "consensus_status": "unreviewed",
                        "knowledge_entry_id": None,
                        "knowledge_snapshot": None,
                    },
                    "review_history": [],
                }
                snvs.append(snv)
        return snvs

    # ------------------------------------------------------------------
    # QC gate
    # ------------------------------------------------------------------

    @staticmethod
    def evaluate_qc_gate(
        qc_metrics: dict,
        assay_config: dict,
    ) -> tuple[str, list[str]]:
        """Evaluate QC metrics against assay thresholds.
        Returns (status, failures) where status is 'passed' | 'borderline' | 'failed'.
        """
        failures: list[str] = []
        thresholds = assay_config.get("qc_thresholds", {})

        min_depth = thresholds.get("min_mean_depth", 100)
        actual_depth = qc_metrics.get("mean_depth", 0)
        if actual_depth < min_depth:
            failures.append(
                f"Mean depth {actual_depth} < minimum {min_depth}"
            )

        min_100x = thresholds.get("min_pct_bases_100x", 80.0)
        actual_100x = qc_metrics.get("pct_bases_100x", 0)
        if actual_100x < min_100x:
            failures.append(
                f"% bases ≥100x {actual_100x:.1f}% < minimum {min_100x}%"
            )

        max_contamination = thresholds.get("max_contamination", 0.05)
        contamination = qc_metrics.get("contamination_estimate")
        if contamination is not None and contamination > max_contamination:
            failures.append(
                f"Contamination {contamination:.3f} > maximum {max_contamination}"
            )

        min_purity = thresholds.get("min_tumor_purity")
        purity = qc_metrics.get("tumor_purity")
        if min_purity is not None and purity is not None and purity < min_purity:
            failures.append(
                f"Tumour purity {purity:.2f} < minimum {min_purity}"
            )

        if not failures:
            return "passed", []

        # Borderline: only soft metrics failed (purity / contamination near limit)
        soft_keywords = ("Contamination", "purity")
        all_soft = all(
            any(kw in f for kw in soft_keywords) for f in failures
        )
        return ("borderline" if all_soft else "failed"), failures

    # ------------------------------------------------------------------
    # Callset supersession
    # ------------------------------------------------------------------

    @staticmethod
    def supersede_existing(
        db,
        sample_assay_id: str,
        actor_user_id: str,
        actor_username: str,
    ) -> None:
        """Mark any previously imported callset for this case as superseded."""
        db.callsets.update_many(
            {"sample_assay_id": sample_assay_id, "import_status": "imported"},
            {"$set": {"import_status": "superseded", "is_active": False}},
        )
        AuditService.log(
            event_type="callset_superseded",
            actor_user_id=actor_user_id,
            actor_role="bioinformatician",
            target_collection="callsets",
            target_id=sample_assay_id,
            payload={"sample_assay_id": sample_assay_id, "superseded_by": actor_username},
        )

    # ------------------------------------------------------------------
    # Main import entry point
    # ------------------------------------------------------------------

    @staticmethod
    def import_vcf(
        vcf_path: str,
        qc_json_path: str | None,
        sample_assay_id: str,
        imported_by_user_id: str,
        imported_by_username: str,
        bcftools_bin: str = "bcftools",
        vep_bin: str = "vep",
        vep_cache: str = "",
        ref_fasta: str = "",
        skip_normalise: bool = False,
        skip_annotate: bool = False,
    ) -> dict:
        """
        Full VCF import pipeline. Returns the created callset document.
        Raises IngestionError on failure.
        """
        import tempfile

        db = mongo_client.db
        now = datetime.utcnow().isoformat() + "Z"

        # --- Idempotency ---
        checksum = IngestionService.compute_checksum(vcf_path)
        if IngestionService.already_imported(checksum):
            raise IngestionError(
                f"VCF already imported (checksum {checksum[:12]}…). Skipping."
            )

        # --- Validate sample_assay ---
        assay = db.sample_assays.find_one(
            {"sample_assay_id": sample_assay_id}, {"_id": 0}
        )
        if not assay:
            raise IngestionError(
                f"sample_assay_id {sample_assay_id!r} not found."
            )

        assay_config = (
            AssayConfigService.get_active_config(assay["assay_id"]) or {}
        )

        # --- Supersede existing callsets ---
        existing = db.callsets.find_one(
            {"sample_assay_id": sample_assay_id, "import_status": "imported"},
            {"_id": 1},
        )
        if existing:
            IngestionService.supersede_existing(
                db, sample_assay_id, imported_by_user_id, imported_by_username
            )

        callset_id = "CS_" + str(uuid.uuid4())[:8].upper()

        callset: dict = {
            "callset_id": callset_id,
            "sample_assay_id": sample_assay_id,
            "vcf_path": vcf_path,
            "vcf_checksum": checksum,
            "normalised_vcf_path": "",
            "qc_metrics": {},
            "qc_status": "pending",
            "qc_failures": [],
            "annotation_vep_version": "",
            "import_status": "pending",
            "import_error": "",
            "is_active": True,
            "raw_counts": {"snv": 0, "cnv": 0, "sv": 0},
            "created_at": now,
            "imported_by": imported_by_user_id,
            "imported_by_username": imported_by_username,
        }
        db.callsets.insert_one(callset)
        callset.pop("_id", None)

        try:
            with tempfile.TemporaryDirectory() as tmp:

                # --- Normalise ---
                if skip_normalise:
                    normalised_vcf = vcf_path
                else:
                    normalised_vcf = os.path.join(tmp, "normalised.vcf.gz")
                    IngestionService._set_import_status(db, callset_id, "normalising")
                    IngestionService.run_bcftools_norm(
                        vcf_path, normalised_vcf, ref_fasta, bcftools_bin
                    )
                    db.callsets.update_one(
                        {"callset_id": callset_id},
                        {"$set": {"normalised_vcf_path": normalised_vcf}},
                    )

                # --- Annotate ---
                if skip_annotate:
                    annotated_vcf = normalised_vcf
                    vep_version = "skipped"
                else:
                    annotated_vcf = os.path.join(tmp, "annotated.vcf")
                    IngestionService._set_import_status(db, callset_id, "annotating")
                    vep_version = IngestionService.run_vep(
                        normalised_vcf, annotated_vcf, vep_bin, vep_cache
                    )
                    db.callsets.update_one(
                        {"callset_id": callset_id},
                        {"$set": {"annotation_vep_version": vep_version}},
                    )

                # --- Parse SNVs ---
                snvs = IngestionService.parse_vep_vcf(
                    annotated_vcf, sample_assay_id, callset_id
                )
                for snv in snvs:
                    snv["annotation_version"] = vep_version
                if snvs:
                    db.snvs_raw.insert_many(snvs)

                # --- Parse QC JSON ---
                qc_metrics: dict = {}
                if qc_json_path and os.path.exists(qc_json_path):
                    with open(qc_json_path) as fh:
                        qc_metrics = json.load(fh)

                # --- QC gate ---
                qc_status, qc_failures = IngestionService.evaluate_qc_gate(
                    qc_metrics, assay_config
                )

                now2 = datetime.utcnow().isoformat() + "Z"
                if qc_status == "passed":
                    new_assay_status = "analysis_ready"
                    note = "QC passed — analysis ready"
                elif qc_status == "borderline":
                    new_assay_status = "pending_qc"
                    note = f"QC borderline: {'; '.join(qc_failures)}"
                else:
                    new_assay_status = "qc_failed"
                    note = f"QC failed: {'; '.join(qc_failures)}"

                # --- Finalise callset ---
                db.callsets.update_one(
                    {"callset_id": callset_id},
                    {
                        "$set": {
                            "qc_metrics": qc_metrics,
                            "qc_status": qc_status,
                            "qc_failures": qc_failures,
                            "import_status": "imported",
                            "raw_counts": {
                                "snv": len(snvs),
                                "cnv": 0,
                                "sv": 0,
                            },
                        }
                    },
                )

                # --- Advance sample_assay status ---
                db.sample_assays.update_one(
                    {"sample_assay_id": sample_assay_id},
                    {
                        "$set": {
                            "status": new_assay_status,
                            "active_callset_id": callset_id,
                        },
                        "$push": {
                            "state_history": {
                                "status": new_assay_status,
                                "timestamp": now2,
                                "actor_user_id": imported_by_user_id,
                                "note": note,
                            }
                        },
                    },
                )

                AuditService.log(
                    event_type="vcf_imported",
                    actor_user_id=imported_by_user_id,
                    actor_role="bioinformatician",
                    target_collection="callsets",
                    target_id=callset_id,
                    payload={
                        "callset_id": callset_id,
                        "sample_assay_id": sample_assay_id,
                        "qc_status": qc_status,
                        "snv_count": len(snvs),
                        "vcf_checksum": checksum,
                    },
                )

                return db.callsets.find_one(
                    {"callset_id": callset_id}, {"_id": 0}
                )

        except IngestionError:
            IngestionService._set_import_status(db, callset_id, "failed")
            raise
        except Exception as exc:
            IngestionService._set_import_status(
                db, callset_id, "failed", str(exc)
            )
            raise IngestionError(f"Unexpected import error: {exc}") from exc

    # ------------------------------------------------------------------
    # Callset queries
    # ------------------------------------------------------------------

    @staticmethod
    def get_callsets(sample_assay_id: str) -> list[dict]:
        db = mongo_client.db
        return list(
            db.callsets.find(
                {"sample_assay_id": sample_assay_id},
                {"_id": 0},
            ).sort("created_at", -1)
        )

    @staticmethod
    def get_callset(callset_id: str) -> dict | None:
        db = mongo_client.db
        return db.callsets.find_one({"callset_id": callset_id}, {"_id": 0})
