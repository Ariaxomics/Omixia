import click
from flask.cli import with_appcontext

from src.services.ingestion import IngestionError, IngestionService


def register_import_vcf_command(app) -> None:

    @app.cli.command("import-vcf")
    @click.option("--vcf", required=True, help="Path to VCF or VCF.GZ file")
    @click.option("--qc", default=None, help="Path to QC JSON file (optional)")
    @click.option(
        "--sample-assay-id", required=True,
        help="Target sample_assay_id",
    )
    @click.option(
        "--user-id", default="cli",
        help="User ID for the importing bioinformatician",
    )
    @click.option(
        "--username", default="cli",
        help="Username for the importing bioinformatician",
    )
    @click.option(
        "--bcftools", default="bcftools",
        envvar="BCFTOOLS_BIN",
        help="Path to bcftools binary",
    )
    @click.option(
        "--vep", default="vep",
        envvar="VEP_BIN",
        help="Path to Ensembl VEP binary",
    )
    @click.option(
        "--vep-cache", default="",
        envvar="VEP_CACHE_DIR",
        help="Path to VEP cache directory",
    )
    @click.option(
        "--ref-fasta", default="",
        envvar="REF_FASTA",
        help="GRCh38 reference FASTA for bcftools norm",
    )
    @click.option(
        "--skip-normalise", is_flag=True,
        help="Skip bcftools normalisation (dev/testing only)",
    )
    @click.option(
        "--skip-annotate", is_flag=True,
        help="Skip VEP annotation (dev/testing only)",
    )
    @with_appcontext
    def import_vcf(
        vcf, qc, sample_assay_id, user_id, username,
        bcftools, vep, vep_cache, ref_fasta,
        skip_normalise, skip_annotate,
    ):
        """Import a VCF file through the normalisation + annotation pipeline."""
        click.echo(f"Importing {vcf!r} → sample_assay {sample_assay_id!r} …")
        try:
            callset = IngestionService.import_vcf(
                vcf_path=vcf,
                qc_json_path=qc,
                sample_assay_id=sample_assay_id,
                imported_by_user_id=user_id,
                imported_by_username=username,
                bcftools_bin=bcftools,
                vep_bin=vep,
                vep_cache=vep_cache,
                ref_fasta=ref_fasta,
                skip_normalise=skip_normalise,
                skip_annotate=skip_annotate,
            )
            counts = callset.get("raw_counts", {})
            click.echo(
                f"Done. Callset: {callset['callset_id']}  "
                f"QC: {callset['qc_status']}  "
                f"SNVs: {counts.get('snv', 0)}"
            )
            if callset.get("qc_failures"):
                for f in callset["qc_failures"]:
                    click.echo(f"  QC failure: {f}", err=True)
        except IngestionError as exc:
            click.echo(f"Error: {exc}", err=True)
            raise SystemExit(1)
