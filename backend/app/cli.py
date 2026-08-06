import typer

from src.cli.create_user import create_user as _create_user
from src.cli.import_vcf import import_vcf as _import_vcf
from src.cli.load_demo import load_demo_data
from src.cli.watcher import run_watcher as _run_watcher
from src.extensions import mongo_client, redis_client

app = typer.Typer(help="Omixia management CLI")


@app.callback()
def _init(ctx: typer.Context) -> None:
    mongo_client.init_app()
    redis_client.init_app()


@app.command("load-demo")
def load_demo() -> None:
    """Load demo fixtures into MongoDB."""
    load_demo_data()


app.command("create-user")(_create_user)
app.command("import-vcf")(_import_vcf)
app.command("run-watcher")(_run_watcher)


if __name__ == "__main__":
    app()
