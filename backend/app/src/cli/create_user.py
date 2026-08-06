import typer

from src.services.users import VALID_ROLES, UserService


def create_user(
    username: str = typer.Option(..., help="Login username"),
    email: str = typer.Option(..., help="User email address"),
    full_name: str = typer.Option(..., help="Display name"),
    role: str = typer.Option(..., help=f"User role. One of: {', '.join(VALID_ROLES)}"),
    password: str = typer.Option(..., prompt=True, hide_input=True, confirmation_prompt=True, help="Login password (min 12 chars)"),
) -> None:
    """Create a new Omixia user."""
    if role not in VALID_ROLES:
        raise typer.BadParameter(f"Invalid role '{role}'. Must be one of: {', '.join(VALID_ROLES)}", param_hint="--role")

    if len(password) < 12:
        raise typer.BadParameter("Password must be at least 12 characters.", param_hint="--password")

    try:
        user = UserService.create_user(
            username=username,
            email=email,
            role=role,
            full_name=full_name,
            password=password,
        )
        typer.echo(f"Created user '{user['username']}' (role: {user['role']}, id: {user['user_id']})")
    except ValueError as e:
        typer.echo(f"Error: {e}", err=True)
        raise typer.Exit(code=1) from e
