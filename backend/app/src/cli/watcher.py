"""
Directory watcher for VCF file ingestion.

Expected inbox layout:
  <watch_dir>/
    sample123.vcf.gz        ← VCF (or .vcf)
    sample123.qc.json       ← QC metrics (optional but recommended)
    sample123.meta.json     ← Required: { "sample_assay_id": "SA_..." }
  processed/               ← successfully imported files are moved here
  failed/                  ← files that failed import are moved here
"""
import json
import os
import time

import typer

from src.services.ingestion import IngestionError, IngestionService


def run_watcher(
    watch_dir: str = typer.Option("/data/vcf_inbox", envvar="VCF_IMPORT_DIR", help="Directory to watch for new VCF + meta.json pairs"),
    interval: int = typer.Option(900, help="Poll interval in seconds (15 min default)"),
    user_id: str = typer.Option("watcher", envvar="WATCHER_USER_ID"),
    username: str = typer.Option("watcher", envvar="WATCHER_USERNAME"),
    bcftools: str = typer.Option("bcftools", envvar="BCFTOOLS_BIN"),
    vep: str = typer.Option("vep", envvar="VEP_BIN"),
    vep_cache: str = typer.Option("", envvar="VEP_CACHE_DIR"),
    ref_fasta: str = typer.Option("", envvar="REF_FASTA"),
    skip_normalise: bool = typer.Option(False),
    skip_annotate: bool = typer.Option(False),
    once: bool = typer.Option(False, help="Scan once and exit (useful for cron invocation)"),
) -> None:
    """Poll a directory every <interval> seconds for new VCF files."""
    typer.echo(f"Watcher started — watching {watch_dir!r}  interval={interval}s")
    kwargs = dict(
        watch_dir=watch_dir,
        user_id=user_id,
        username=username,
        bcftools=bcftools,
        vep=vep,
        vep_cache=vep_cache,
        ref_fasta=ref_fasta,
        skip_normalise=skip_normalise,
        skip_annotate=skip_annotate,
    )
    while True:
        _scan(**kwargs)
        if once:
            break
        time.sleep(interval)


def _scan(
    watch_dir, user_id, username,
    bcftools, vep, vep_cache, ref_fasta,
    skip_normalise, skip_annotate,
):
    if not os.path.isdir(watch_dir):
        typer.echo(f"  Watch directory {watch_dir!r} does not exist — skipping scan.")
        return

    processed_dir = os.path.join(watch_dir, "processed")
    failed_dir = os.path.join(watch_dir, "failed")

    for fname in sorted(os.listdir(watch_dir)):
        if not (fname.endswith(".vcf") or fname.endswith(".vcf.gz")):
            continue

        vcf_path = os.path.join(watch_dir, fname)
        base = fname[:-7] if fname.endswith(".vcf.gz") else fname[:-4]
        qc_path = os.path.join(watch_dir, base + ".qc.json")
        meta_path = os.path.join(watch_dir, base + ".meta.json")

        if not os.path.exists(meta_path):
            typer.echo(f"  Skipping {fname!r}: missing {base}.meta.json")
            continue

        try:
            with open(meta_path) as fh:
                meta = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            typer.echo(f"  Skipping {fname!r}: bad meta.json — {exc}")
            continue

        sample_assay_id = meta.get("sample_assay_id", "")
        if not sample_assay_id:
            typer.echo(f"  Skipping {fname!r}: meta.json missing 'sample_assay_id'")
            continue

        typer.echo(f"  Processing {fname!r} → {sample_assay_id!r}")
        try:
            callset = IngestionService.import_vcf(
                vcf_path=vcf_path,
                qc_json_path=qc_path if os.path.exists(qc_path) else None,
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
                f"    OK  {callset['callset_id']}  "
                f"QC={callset['qc_status']}  "
                f"SNVs={counts.get('snv', 0)}"
            )
            _move_files(vcf_path, qc_path, meta_path, processed_dir, base, fname)

        except IngestionError as exc:
            msg = str(exc)
            if "already imported" in msg.lower():
                typer.echo(f"    Skipped (already imported): {fname!r}")
                _move_files(vcf_path, qc_path, meta_path, processed_dir, base, fname)
            else:
                typer.echo(f"    FAILED: {msg}", err=True)
                _move_files(vcf_path, qc_path, meta_path, failed_dir, base, fname)


def _move_files(vcf_path, qc_path, meta_path, dest_dir, base, fname):
    os.makedirs(dest_dir, exist_ok=True)
    _try_move(vcf_path, os.path.join(dest_dir, fname))
    _try_move(qc_path, os.path.join(dest_dir, base + ".qc.json"))
    _try_move(meta_path, os.path.join(dest_dir, base + ".meta.json"))


def _try_move(src, dst):
    if os.path.exists(src):
        try:
            os.rename(src, dst)
        except OSError:
            pass
