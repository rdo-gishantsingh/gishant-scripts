import typer
from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm
from rich.table import Table

from gishant_scripts.ayon.common import AYONConnectionError, setup_ayon_connection

try:
    import ayon_api
except ImportError:
    ayon_api = None

# Create Typer app
app = typer.Typer(help="Ayon CRUD operations")
console = Console()

# Global state for environment flags
_use_local = False
_use_dev = False


@app.callback()
def main(
    local: bool = typer.Option(
        False, "--local", help="Use local environment (AYON_SERVER_URL_LOCAL, AYON_API_KEY_LOCAL)"
    ),
    dev: bool = typer.Option(False, "--dev", help="Use dev environment (AYON_SERVER_URL_DEV, AYON_API_KEY_DEV)"),
):
    """Ayon CRUD operations with environment selection."""
    global _use_local, _use_dev
    _use_local = local
    _use_dev = dev


def get_connection():
    """Establish connection to Ayon server."""
    try:
        setup_ayon_connection(console, use_local=_use_local, use_dev=_use_dev)
        return ayon_api
    except AYONConnectionError as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(code=1)


@app.command("list-projects")
def list_projects():
    """List all projects in Ayon."""
    api = get_connection()

    try:
        projects = list(api.get_projects())

        if not projects:
            console.print("[yellow]No projects found.[/yellow]")
            return

        table = Table(title="Ayon Projects")
        table.add_column("Name", style="cyan")
        table.add_column("Code", style="green")
        table.add_column("Active", style="magenta")

        for project in projects:
            table.add_row(project["name"], project.get("code", "N/A"), str(project.get("active", True)))

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error fetching projects: {e}[/red]")
        raise typer.Exit(code=1)


@app.command("get-project")
def get_project(project_name: str):
    """Get details of a specific project."""
    api = get_connection()

    try:
        project = api.get_project(project_name)
        if not project:
            console.print(f"[red]Project '{project_name}' not found.[/red]")
            raise typer.Exit(code=1)

        console.print(
            Panel(
                f"Name: {project['name']}\n"
                f"Code: {project.get('code', 'N/A')}\n"
                f"Active: {project.get('active', True)}\n"
                f"Folder Structure: {len(project.get('folders', []))} folders",
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
    api = get_connection()

    try:
        console.print(f"[dim]Creating project '{name}' ({code})...[/dim]")
        api.create_project(name, code)
        console.print(f"[green]✓ Project '{name}' created successfully.[/green]")

    except Exception as e:
        console.print(f"[red]Error creating project: {e}[/red]")
        raise typer.Exit(code=1)


@app.command("delete-project")
def delete_project(project_name: str):
    """Delete a project."""
    api = get_connection()

    if not Confirm.ask(f"Are you sure you want to delete project '{project_name}'?"):
        console.print("[yellow]Operation cancelled.[/yellow]")
        return

    try:
        api.delete_project(project_name)
        console.print(f"[green]✓ Project '{project_name}' deleted successfully.[/green]")

    except Exception as e:
        console.print(f"[red]Error deleting project: {e}[/red]")
        raise typer.Exit(code=1)


@app.command("list-users")
def list_users():
    """List all users."""
    api = get_connection()

    try:
        users = list(api.get_users())

        if not users:
            console.print("[yellow]No users found.[/yellow]")
            return

        table = Table(title="Ayon Users")
        table.add_column("Username", style="cyan")
        table.add_column("Full Name", style="green")
        table.add_column("Role", style="magenta")

        for user in users:
            # Handle different user object structures if needed
            username = user.get("name", "Unknown")
            fullname = user.get("attrib", {}).get("fullName", "N/A")
            # Role might be complex, simplifying for now
            roles = user.get("roles", {})
            role_str = ", ".join(roles.keys()) if roles else "Default"

            table.add_row(username, fullname, role_str)

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error fetching users: {e}[/red]")
        raise typer.Exit(code=1)


# Import batch data generator commands (lazy import to avoid circular dependencies)
def _register_batch_commands():
    """Register batch data generation commands."""
    from gishant_scripts.ayon.batch_data_generator import generate_data_cli, simulate_load_cli

    app.command("generate-batch-data", help="Generate batch test data for load testing")(generate_data_cli)
    app.command("simulate-load", help="Simulate concurrent user load to stress-test sync service")(simulate_load_cli)


def _register_representation_commands():
    """Register representation commands."""
    from gishant_scripts.ayon.cli.get_representation_cli import get_representation_cli

    app.command("get-representation", help="Get representation for a product in a folder")(get_representation_cli)


def _register_restore_commands():
    """Register database restore commands."""
    from gishant_scripts.ayon.restore_db_cli import restore

    app.command("restore-db", help="Restore AYON database from backup file")(restore)


# Register batch commands
_register_batch_commands()

# Register representation commands
_register_representation_commands()

# Register restore commands
_register_restore_commands()

if __name__ == "__main__":
    app()
