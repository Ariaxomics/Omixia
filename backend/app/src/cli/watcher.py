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

import click
from flask.cli import with_appcontext

from src.services.ingestion import IngestionError, IngestionService


def register_watcher_command(app) -> None:

    @app.cli.command("run-watcher")
    @click.option(
        "--watch-dir",
        envvar="VCF_IMPORT_DIR",
        default="/data/vcf_inbox",
        show_default=True,
        help="Directory to watch for new VCF + meta.json pairs",
    )
    @click.option(
        "--interval", default=900, show_default=True,
        help="Poll interval in seconds (15 min default)",
    )
    @click.option("--user-id", default="watcher", envvar="WATCHER_USER_ID")
    @click.option("--username", default="watcher", envvar="WATCHER_USERNAME")
    @click.option("--bcftools", default="bcftools", envvar="BCFTOOLS_BIN")
    @click.option("--vep", default="vep", envvar="VEP_BIN")
    @click.option("--vep-cache", default="", envvar="VEP_CACHE_DIR")
    @click.option("--ref-fasta", default="", envvar="REF_FASTA")
    @click.option("--skip-normalise", is_flag=True)
    @click.option("--skip-annotate", is_flag=True)
    @click.option(
        "--once", is_flag=True,
        help="Scan once and exit (useful for cron invocation)",
    )
    @with_appcontext
    def run_watcher(
        watch_dir, interval, user_id, username,
        bcftools, vep, vep_cache, ref_fasta,
        skip_normalise, skip_annotate, once,
    ):
        """Poll a directory every <interval> seconds for new VCF files."""
        click.echo(
            f"Watcher started — watching {watch_dir!r}  interval={interval}s"
        )
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
        click.echo(
            f"  Watch directory {watch_dir!r} does not exist — skipping scan."
        )
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
            click.echo(f"  Skipping {fname!r}: missing {base}.meta.json")
            continue

        try:
            with open(meta_path) as fh:
                meta = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            click.echo(f"  Skipping {fname!r}: bad meta.json — {exc}")
            continue

        sample_assay_id = meta.get("sample_assay_id", "")
        if not sample_assay_id:
            click.echo(
                f"  Skipping {fname!r}: meta.json missing 'sample_assay_id'"
            )
            continue

        click.echo(f"  Processing {fname!r} → {sample_assay_id!r}")
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
            click.echo(
                f"    OK  {callset['callset_id']}  "
                f"QC={callset['qc_status']}  "
                f"SNVs={counts.get('snv', 0)}"
            )
            _move_files(vcf_path, qc_path, meta_path, processed_dir, base, fname)

        except IngestionError as exc:
            msg = str(exc)
            if "already imported" in msg.lower():
                click.echo(f"    Skipped (already imported): {fname!r}")
                _move_files(vcf_path, qc_path, meta_path, processed_dir, base, fname)
            else:
                click.echo(f"    FAILED: {msg}", err=True)
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
