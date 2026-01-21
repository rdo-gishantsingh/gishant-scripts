import os

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from gishant_scripts.common.config import AppConfig

try:
    import gazu
except ImportError:
    gazu = None

# Create Typer app
app = typer.Typer(help="Kitsu CRUD operations")
console = Console()


def get_connection():
    """Establish connection to Kitsu server."""
    # Load environment variables via AppConfig
    AppConfig()

    if gazu is None:
        console.print("[red]Error: gazu not installed.[/red]")
        raise typer.Exit(code=1)

    # Check for local test env vars first
    host = os.getenv("KITSU_API_URL_LOCAL") or os.getenv("KITSU_API_URL")
    login = os.getenv("KITSU_LOGIN_LOCAL") or os.getenv("KITSU_LOGIN")
    password = os.getenv("KITSU_PASSWORD_LOCAL") or os.getenv("KITSU_PASSWORD")

    if not host:
        console.print("[red]Error: KITSU_API_URL must be set.[/red]")
        console.print("[yellow]Tip: Use KITSU_API_URL_LOCAL for testing.[/yellow]")
        raise typer.Exit(code=1)

    try:
        # Initialize gazu
        if not gazu.client.host_is_valid(host):
            # Sometimes host_is_valid returns False even if valid if /api is missing or present unexpectedly
            # We'll try setting it anyway and catch connection errors later
            pass

        gazu.set_host(host)

        if login and password:
            gazu.log_in(login, password)
        else:
            # If no credentials provided, check if we have a token or prompt?
            # For now, require credentials in env for automation friendliness
            console.print("[yellow]Warning: No credentials provided. Some operations may fail.[/yellow]")

        return gazu
    except Exception as e:
        console.print(f"[red]Failed to connect to Kitsu: {e}[/red]")
        raise typer.Exit(code=1)


@app.command("login")
def login_cmd(
    host: str = typer.Option(..., prompt="Kitsu URL"),
    username: str = typer.Option(..., prompt="Username/Email"),
    password: str = typer.Option(..., prompt="Password", hide_input=True),
):
    """Interactive login to Kitsu."""
    if gazu is None:
        console.print("[red]Error: gazu not installed.[/red]")
        raise typer.Exit(code=1)

    try:
        gazu.set_host(host)
        gazu.log_in(username, password)
        console.print("[green]✓ Successfully logged in to Kitsu.[/green]")
        # Note: Gazu stores tokens in memory or ~/.gazu/tokens.json depending on version/config
        # We might need to persist this if we want it to last between runs without env vars

    except Exception as e:
        console.print(f"[red]Login failed: {e}[/red]")
        raise typer.Exit(code=1)


@app.command("list-projects")
def list_projects():
    """List all projects in Kitsu."""
    get_connection()

    try:
        projects = gazu.project.all_open_projects()

        if not projects:
            console.print("[yellow]No open projects found.[/yellow]")
            return

        table = Table(title="Kitsu Projects")
        table.add_column("Name", style="cyan")
        table.add_column("Code", style="green")
        table.add_column("Status", style="magenta")

        for project in projects:
            table.add_row(project["name"], project.get("code", "N/A"), project.get("status", "Open"))

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error fetching projects: {e}[/red]")
        raise typer.Exit(code=1)


@app.command("get-project")
def get_project(project_name: str):
    """Get details of a specific project."""
    get_connection()

    try:
        project = gazu.project.get_project_by_name(project_name)
        if not project:
            console.print(f"[red]Project '{project_name}' not found.[/red]")
            raise typer.Exit(code=1)

        console.print(
            Panel(
                f"Name: {project['name']}\n"
                f"Code: {project.get('code', 'N/A')}\n"
                f"Status: {project.get('status', 'N/A')}\n"
                f"ID: {project['id']}",
                title=f"Project Details: {project_name}",
                border_style="blue",
            )
        )

    except Exception as e:
        console.print(f"[red]Error fetching project: {e}[/red]")
        raise typer.Exit(code=1)


@app.command("create-project")
def create_project(
    name: str = typer.Option(..., prompt="Project Name"),
    code: str = typer.Option(..., prompt="Project Code"),
):
    """Create a new project."""
    get_connection()

    try:
        console.print(f"[dim]Creating project '{name}' ({code})...[/dim]")
        gazu.project.new_project(name, code)
        console.print(f"[green]✓ Project '{name}' created successfully.[/green]")

    except Exception as e:
        console.print(f"[red]Error creating project: {e}[/red]")
        raise typer.Exit(code=1)


@app.command("update-project")
def update_project(
    project_name: str = typer.Argument(..., help="Name of the project to update"),
    new_name: str | None = typer.Option(None, help="New name for the project"),
    active: bool | None = typer.Option(None, help="Set project active status"),
):
    """Update a project."""
    get_connection()

    try:
        project = gazu.project.get_project_by_name(project_name)
        if not project:
            console.print(f"[red]Project '{project_name}' not found.[/red]")
            raise typer.Exit(code=1)

        updates = {}
        if new_name:
            updates["name"] = new_name
        if active is not None:
            # Kitsu uses 'closed' status usually, but let's see what the API expects
            # For now assuming we just update the dict
            if active:
                updates["status"] = "open"
            else:
                updates["status"] = "closed"

        if not updates:
            console.print("[yellow]No updates specified.[/yellow]")
            return

        gazu.project.update_project(project, updates)
        console.print(f"[green]✓ Project '{project_name}' updated successfully.[/green]")

    except Exception as e:
        console.print(f"[red]Error updating project: {e}[/red]")
        raise typer.Exit(code=1)


# Import batch data generator commands (lazy import to avoid circular dependencies)
def _register_batch_commands():
    """Register batch data generation commands."""
    from gishant_scripts.kitsu.batch_data_generator import generate_data_cli, simulate_load_cli

    app.command("generate-batch-data", help="Generate batch test data for load testing")(generate_data_cli)
    app.command("simulate-load", help="Simulate concurrent user load to stress-test sync service")(simulate_load_cli)


def _register_restore_commands():
    """Register database restore commands."""
    from gishant_scripts.kitsu.restore_db_cli import restore

    app.command("restore-db", help="Restore Kitsu database from backup file")(restore)


# Register batch commands
_register_batch_commands()

# Register restore commands
_register_restore_commands()

if __name__ == "__main__":
    app()
