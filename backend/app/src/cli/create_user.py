import click
from flask import Flask

from src.services.users import VALID_ROLES, UserService


def register_create_user_command(app: Flask) -> None:
    @app.cli.command("create-user")
    @click.option("--username", required=True, help="Login username")
    @click.option("--email", required=True, help="User email address")
    @click.option("--full-name", required=True, help="Display name")
    @click.option(
        "--role",
        required=True,
        type=click.Choice(VALID_ROLES),
        help="User role",
    )
    @click.password_option("--password", help="Login password (min 12 chars)")
    def create_user(username: str, email: str, full_name: str, role: str, password: str) -> None:
        """Create a new Omixia user."""
        if len(password) < 12:
            raise click.BadParameter("Password must be at least 12 characters.", param_hint="--password")

        with app.app_context():
            try:
                user = UserService.create_user(
                    username=username,
                    email=email,
                    role=role,
                    full_name=full_name,
                    password=password,
                )
                click.echo(f"Created user '{user['username']}' (role: {user['role']}, id: {user['user_id']})")
            except ValueError as e:
                raise click.ClickException(str(e))
