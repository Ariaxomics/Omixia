import typer

from src.services.ingestion import IngestionError, IngestionService


def import_vcf(
    vcf: str = typer.Option(..., help="Path to VCF or VCF.GZ file"),
    qc: str = typer.Option(None, help="Path to QC JSON file (optional)"),
    sample_assay_id: str = typer.Option(..., help="Target sample_assay_id"),
    user_id: str = typer.Option("cli", help="User ID for the importing bioinformatician"),
    username: str = typer.Option("cli", help="Username for the importing bioinformatician"),
    bcftools: str = typer.Option("bcftools", envvar="BCFTOOLS_BIN", help="Path to bcftools binary"),
    vep: str = typer.Option("vep", envvar="VEP_BIN", help="Path to Ensembl VEP binary"),
    vep_cache: str = typer.Option("", envvar="VEP_CACHE_DIR", help="Path to VEP cache directory"),
    ref_fasta: str = typer.Option("", envvar="REF_FASTA", help="GRCh38 reference FASTA for bcftools norm"),
    skip_normalise: bool = typer.Option(False, help="Skip bcftools normalisation (dev/testing only)"),
    skip_annotate: bool = typer.Option(False, help="Skip VEP annotation (dev/testing only)"),
) -> None:
    """Import a VCF file through the normalisation + annotation pipeline."""
    typer.echo(f"Importing {vcf!r} → sample_assay {sample_assay_id!r} …")
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
        typer.echo(
            f"Done. Callset: {callset['callset_id']}  "
            f"QC: {callset['qc_status']}  "
            f"SNVs: {counts.get('snv', 0)}"
        )
        if callset.get("qc_failures"):
            for f in callset["qc_failures"]:
                typer.echo(f"  QC failure: {f}", err=True)
    except IngestionError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from exc
