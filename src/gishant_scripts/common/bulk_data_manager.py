"""Unified bulk data manager for AYON and Kitsu.

This script orchestrates cleanup and bulk data generation across both AYON and Kitsu
systems with proper formatting and synchronization.
"""

import sys
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn

console = Console()
app = typer.Typer(help="Unified bulk data management for AYON and Kitsu")


def cleanup_all(prefix: str = "test", dry_run: bool = False, skip_confirmation: bool = False) -> dict:
    """Clean up test data from both AYON and Kitsu.

    Args:
        prefix: Prefix used for test data
        dry_run: If True, only show what would be deleted
        skip_confirmation: If True, skip confirmation prompts

    Returns:
        Combined cleanup results
    """
    results = {
        "ayon": {"success": False, "projects_deleted": 0, "users_deleted": 0, "errors": []},
        "kitsu": {"success": False, "projects_deleted": 0, "users_deleted": 0, "errors": []},
    }

    if not dry_run and not skip_confirmation:
        console.print(Panel(
            f"[bold yellow]WARNING: This will delete ALL test data with prefix '{prefix}' from:[/bold yellow]\n"
            "  • AYON (projects, users)\n"
            "  • Kitsu (projects, users)\n\n"
            "[bold red]This action cannot be undone![/bold red]",
            title="⚠️  Cleanup Confirmation",
            border_style="red"
        ))
        response = typer.confirm("Are you absolutely sure you want to continue?")
        if not response:
            console.print("[yellow]Cleanup cancelled.[/yellow]")
            return results

    # Cleanup AYON
    console.print("\n[bold cyan]━━━ Cleaning up AYON ━━━[/bold cyan]")
    try:
        from gishant_scripts.ayon.batch_data_generator import get_connection as get_ayon_connection
        from gishant_scripts.ayon.batch_data_generator import cleanup_test_data as cleanup_ayon

        api = get_ayon_connection()
        ayon_results = cleanup_ayon(api, prefix, dry_run)
        results["ayon"]["success"] = True
        results["ayon"]["projects_deleted"] = ayon_results.get("projects_deleted", 0)
        results["ayon"]["users_deleted"] = ayon_results.get("users_deleted", 0)
        results["ayon"]["errors"] = ayon_results.get("errors", [])

        if dry_run:
            console.print("[yellow]AYON dry run completed[/yellow]")
        else:
            console.print(f"[green]✓ AYON cleanup completed: {ayon_results['projects_deleted']} projects, {ayon_results['users_deleted']} users deleted[/green]")
    except Exception as e:
        error_msg = f"Error during AYON cleanup: {e}"
        results["ayon"]["errors"].append(error_msg)
        console.print(f"[red]✗ {error_msg}[/red]")

    # Cleanup Kitsu
    console.print("\n[bold cyan]━━━ Cleaning up Kitsu ━━━[/bold cyan]")
    try:
        from gishant_scripts.kitsu.batch_data_generator import get_connection as get_kitsu_connection
        from gishant_scripts.kitsu.batch_data_generator import cleanup_test_data as cleanup_kitsu

        get_kitsu_connection()
        kitsu_results = cleanup_kitsu(prefix, dry_run)
        results["kitsu"]["success"] = True
        results["kitsu"]["projects_deleted"] = kitsu_results.get("projects_deleted", 0)
        results["kitsu"]["users_deleted"] = kitsu_results.get("users_deleted", 0)
        results["kitsu"]["errors"] = kitsu_results.get("errors", [])

        if dry_run:
            console.print("[yellow]Kitsu dry run completed[/yellow]")
        else:
            console.print(f"[green]✓ Kitsu cleanup completed: {kitsu_results['projects_deleted']} projects, {kitsu_results['users_deleted']} users deleted[/green]")
    except Exception as e:
        error_msg = f"Error during Kitsu cleanup: {e}"
        results["kitsu"]["errors"].append(error_msg)
        console.print(f"[red]✗ {error_msg}[/red]")

    return results


def generate_all(
    num_projects: int = 1,
    num_sequences: int = 5,
    num_shots: int = 10,
    num_tasks: int = 3,
    num_users: int = 5,
    batch_size: int = 10,
    prefix: str = "test",
) -> dict:
    """Generate bulk test data in both AYON and Kitsu with proper formatting.

    Args:
        num_projects: Number of projects to create
        num_sequences: Number of sequences per project
        num_shots: Number of shots per sequence
        num_tasks: Number of tasks per shot
        num_users: Number of users to create
        batch_size: Batch size for operations
        prefix: Prefix for generated names

    Returns:
        Combined generation results
    """
    results = {
        "ayon": {"success": False, "data": None, "errors": []},
        "kitsu": {"success": False, "data": None, "errors": []},
    }

    # Generate in AYON
    console.print("\n[bold cyan]━━━ Generating data in AYON ━━━[/bold cyan]")
    console.print(f"Projects: {num_projects}, Sequences: {num_sequences}, Shots: {num_shots}, Tasks: {num_tasks}, Users: {num_users}")
    try:
        from gishant_scripts.ayon.batch_data_generator import get_connection as get_ayon_connection
        from gishant_scripts.ayon.batch_data_generator import generate_batch_data as generate_ayon

        api = get_ayon_connection()
        ayon_data = generate_ayon(
            api=api,
            num_projects=num_projects,
            num_sequences_per_project=num_sequences,
            num_shots_per_sequence=num_shots,
            num_tasks_per_shot=num_tasks,
            num_users=num_users,
            batch_size=batch_size,
            prefix=prefix,
        )
        results["ayon"]["success"] = True
        results["ayon"]["data"] = ayon_data

        console.print(f"[green]✓ AYON data generated: {len(ayon_data.get('projects', []))} projects, "
                     f"{len(ayon_data.get('sequences', []))} sequences, "
                     f"{len(ayon_data.get('shots', []))} shots, "
                     f"{len(ayon_data.get('tasks', []))} tasks, "
                     f"{len(ayon_data.get('users', []))} users[/green]")
    except Exception as e:
        error_msg = f"Error during AYON data generation: {e}"
        results["ayon"]["errors"].append(error_msg)
        console.print(f"[red]✗ {error_msg}[/red]")
        import traceback
        console.print(f"[dim]{traceback.format_exc()}[/dim]")

    # Generate in Kitsu
    console.print("\n[bold cyan]━━━ Generating data in Kitsu ━━━[/bold cyan]")
    console.print(f"Projects: {num_projects}, Sequences: {num_sequences}, Shots: {num_shots}, Tasks: {num_tasks}, Users: {num_users}")
    try:
        from gishant_scripts.kitsu.batch_data_generator import get_connection as get_kitsu_connection
        from gishant_scripts.kitsu.batch_data_generator import generate_batch_data as generate_kitsu

        get_kitsu_connection()
        kitsu_data = generate_kitsu(
            num_projects=num_projects,
            num_sequences_per_project=num_sequences,
            num_shots_per_sequence=num_shots,
            num_tasks_per_shot=num_tasks,
            num_users=num_users,
            batch_size=batch_size,
            prefix=prefix,
        )
        results["kitsu"]["success"] = True
        results["kitsu"]["data"] = kitsu_data

        console.print(f"[green]✓ Kitsu data generated: {len(kitsu_data.get('projects', []))} projects, "
                     f"{len(kitsu_data.get('sequences', []))} sequences, "
                     f"{len(kitsu_data.get('shots', []))} shots, "
                     f"{len(kitsu_data.get('tasks', []))} tasks, "
                     f"{len(kitsu_data.get('users', []))} users[/green]")
    except Exception as e:
        error_msg = f"Error during Kitsu data generation: {e}"
        results["kitsu"]["errors"].append(error_msg)
        console.print(f"[red]✗ {error_msg}[/red]")
        import traceback
        console.print(f"[dim]{traceback.format_exc()}[/dim]")

    return results


@app.command("cleanup")
def cleanup_cmd(
    prefix: str = typer.Option("test", "--prefix", help="Prefix for test data to clean up"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be deleted without deleting"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
    ayon_only: bool = typer.Option(False, "--ayon-only", help="Only cleanup AYON"),
    kitsu_only: bool = typer.Option(False, "--kitsu-only", help="Only cleanup Kitsu"),
):
    """Clean up test data from AYON and Kitsu."""
    console.print(Panel(
        f"[bold cyan]Bulk Data Cleanup[/bold cyan]\n"
        f"Prefix: {prefix}\n"
        f"Mode: {'Dry Run' if dry_run else 'LIVE'}",
        border_style="cyan"
    ))

    if ayon_only and kitsu_only:
        console.print("[red]Error: Cannot specify both --ayon-only and --kitsu-only[/red]")
        raise typer.Exit(code=1)

    # If specific system requested, handle separately
    if ayon_only:
        console.print("\n[bold cyan]━━━ Cleaning up AYON only ━━━[/bold cyan]")
        try:
            from gishant_scripts.ayon.batch_data_generator import get_connection, cleanup_test_data
            api = get_connection()
            results = cleanup_test_data(api, prefix, dry_run)

            if not dry_run:
                console.print(f"\n[green]✓ Cleanup completed: {results['projects_deleted']} projects, {results['users_deleted']} users deleted[/green]")
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            raise typer.Exit(code=1)
        return

    if kitsu_only:
        console.print("\n[bold cyan]━━━ Cleaning up Kitsu only ━━━[/bold cyan]")
        try:
            from gishant_scripts.kitsu.batch_data_generator import get_connection, cleanup_test_data
            get_connection()
            results = cleanup_test_data(prefix, dry_run)

            if not dry_run:
                console.print(f"\n[green]✓ Cleanup completed: {results['projects_deleted']} projects, {results['users_deleted']} users deleted[/green]")
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            raise typer.Exit(code=1)
        return

    # Cleanup both systems
    results = cleanup_all(prefix, dry_run, yes)

    # Display summary
    console.print("\n" + "=" * 60)
    if dry_run:
        console.print("[yellow]Dry run completed - no data was actually deleted[/yellow]")
    else:
        table = Table(title="🗑️  Cleanup Summary", show_header=True)
        table.add_column("System", style="cyan", width=15)
        table.add_column("Status", style="bold", width=10)
        table.add_column("Projects", style="green", justify="right")
        table.add_column("Users", style="green", justify="right")
        table.add_column("Errors", style="red", justify="right")

        for system in ["ayon", "kitsu"]:
            status = "✓" if results[system]["success"] else "✗"
            style = "green" if results[system]["success"] else "red"
            table.add_row(
                system.upper(),
                f"[{style}]{status}[/{style}]",
                str(results[system]["projects_deleted"]),
                str(results[system]["users_deleted"]),
                str(len(results[system]["errors"]))
            )

        console.print(table)

        # Show errors if any
        total_errors = len(results["ayon"]["errors"]) + len(results["kitsu"]["errors"])
        if total_errors > 0:
            console.print(f"\n[yellow]⚠  Total errors encountered: {total_errors}[/yellow]")


@app.command("generate")
def generate_cmd(
    num_projects: int = typer.Option(1, "--projects", "-p", help="Number of projects to create"),
    num_sequences: int = typer.Option(5, "--sequences", "-s", help="Number of sequences per project"),
    num_shots: int = typer.Option(10, "--shots", help="Number of shots per sequence"),
    num_tasks: int = typer.Option(3, "--tasks", "-t", help="Number of tasks per shot"),
    num_users: int = typer.Option(5, "--users", "-u", help="Number of users to create"),
    batch_size: int = typer.Option(10, "--batch-size", "-b", help="Batch size for operations"),
    prefix: str = typer.Option("test", "--prefix", help="Prefix for generated names"),
    ayon_only: bool = typer.Option(False, "--ayon-only", help="Only generate in AYON"),
    kitsu_only: bool = typer.Option(False, "--kitsu-only", help="Only generate in Kitsu"),
):
    """Generate bulk test data in AYON and Kitsu."""
    console.print(Panel(
        f"[bold cyan]Bulk Data Generation[/bold cyan]\n"
        f"Projects: {num_projects}\n"
        f"Sequences per project: {num_sequences}\n"
        f"Shots per sequence: {num_shots}\n"
        f"Tasks per shot: {num_tasks}\n"
        f"Users: {num_users}\n"
        f"Prefix: {prefix}",
        border_style="cyan"
    ))

    if ayon_only and kitsu_only:
        console.print("[red]Error: Cannot specify both --ayon-only and --kitsu-only[/red]")
        raise typer.Exit(code=1)

    # If specific system requested, handle separately
    if ayon_only:
        console.print("\n[bold cyan]━━━ Generating data in AYON only ━━━[/bold cyan]")
        try:
            from gishant_scripts.ayon.batch_data_generator import get_connection, generate_batch_data
            api = get_connection()
            results = generate_batch_data(
                api=api,
                num_projects=num_projects,
                num_sequences_per_project=num_sequences,
                num_shots_per_sequence=num_shots,
                num_tasks_per_shot=num_tasks,
                num_users=num_users,
                batch_size=batch_size,
                prefix=prefix,
            )

            console.print(f"\n[green]✓ Generation completed[/green]")
            table = Table(title="Generation Results")
            table.add_column("Type", style="cyan")
            table.add_column("Created", style="green")

            table.add_row("Projects", str(len(results.get("projects", []))))
            table.add_row("Sequences", str(len(results.get("sequences", []))))
            table.add_row("Shots", str(len(results.get("shots", []))))
            table.add_row("Tasks", str(len(results.get("tasks", []))))
            table.add_row("Users", str(len(results.get("users", []))))

            console.print(table)
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            import traceback
            console.print(f"[dim]{traceback.format_exc()}[/dim]")
            raise typer.Exit(code=1)
        return

    if kitsu_only:
        console.print("\n[bold cyan]━━━ Generating data in Kitsu only ━━━[/bold cyan]")
        try:
            from gishant_scripts.kitsu.batch_data_generator import get_connection, generate_batch_data
            get_connection()
            results = generate_batch_data(
                num_projects=num_projects,
                num_sequences_per_project=num_sequences,
                num_shots_per_sequence=num_shots,
                num_tasks_per_shot=num_tasks,
                num_users=num_users,
                batch_size=batch_size,
                prefix=prefix,
            )

            console.print(f"\n[green]✓ Generation completed[/green]")
            table = Table(title="Generation Results")
            table.add_column("Type", style="cyan")
            table.add_column("Created", style="green")

            table.add_row("Projects", str(len(results.get("projects", []))))
            table.add_row("Sequences", str(len(results.get("sequences", []))))
            table.add_row("Shots", str(len(results.get("shots", []))))
            table.add_row("Tasks", str(len(results.get("tasks", []))))
            table.add_row("Users", str(len(results.get("users", []))))

            console.print(table)
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")
            import traceback
            console.print(f"[dim]{traceback.format_exc()}[/dim]")
            raise typer.Exit(code=1)
        return

    # Generate in both systems
    results = generate_all(
        num_projects=num_projects,
        num_sequences=num_sequences,
        num_shots=num_shots,
        num_tasks=num_tasks,
        num_users=num_users,
        batch_size=batch_size,
        prefix=prefix,
    )

    # Display summary
    console.print("\n" + "=" * 60)
    table = Table(title="📊 Generation Summary", show_header=True)
    table.add_column("System", style="cyan", width=15)
    table.add_column("Status", style="bold", width=10)
    table.add_column("Projects", justify="right")
    table.add_column("Sequences", justify="right")
    table.add_column("Shots", justify="right")
    table.add_column("Tasks", justify="right")
    table.add_column("Users", justify="right")

    for system in ["ayon", "kitsu"]:
        status = "✓" if results[system]["success"] else "✗"
        style = "green" if results[system]["success"] else "red"
        data = results[system].get("data", {})
        table.add_row(
            system.upper(),
            f"[{style}]{status}[/{style}]",
            str(len(data.get("projects", []))),
            str(len(data.get("sequences", []))),
            str(len(data.get("shots", []))),
            str(len(data.get("tasks", []))),
            str(len(data.get("users", [])))
        )

    console.print(table)

    # Show errors if any
    total_errors = len(results["ayon"]["errors"]) + len(results["kitsu"]["errors"])
    if total_errors > 0:
        console.print(f"\n[yellow]⚠  Total errors encountered: {total_errors}[/yellow]")


@app.command("reset-and-generate")
def reset_and_generate_cmd(
    num_projects: int = typer.Option(1, "--projects", "-p", help="Number of projects to create"),
    num_sequences: int = typer.Option(5, "--sequences", "-s", help="Number of sequences per project"),
    num_shots: int = typer.Option(10, "--shots", help="Number of shots per sequence"),
    num_tasks: int = typer.Option(3, "--tasks", "-t", help="Number of tasks per shot"),
    num_users: int = typer.Option(5, "--users", "-u", help="Number of users to create"),
    batch_size: int = typer.Option(10, "--batch-size", "-b", help="Batch size for operations"),
    prefix: str = typer.Option("test", "--prefix", help="Prefix for generated names"),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
):
    """Clean up existing test data and generate fresh bulk data in both systems."""
    console.print(Panel(
        f"[bold yellow]⚠️  Reset and Generate[/bold yellow]\n\n"
        f"This will:\n"
        f"1. [red]DELETE[/red] all test data with prefix '{prefix}'\n"
        f"2. [green]GENERATE[/green] fresh test data:\n"
        f"   • {num_projects} projects\n"
        f"   • {num_sequences} sequences per project\n"
        f"   • {num_shots} shots per sequence\n"
        f"   • {num_tasks} tasks per shot\n"
        f"   • {num_users} users",
        border_style="yellow"
    ))

    if not yes:
        response = typer.confirm("\nAre you sure you want to continue?")
        if not response:
            console.print("[yellow]Operation cancelled.[/yellow]")
            raise typer.Exit(code=0)

    # Step 1: Cleanup
    console.print("\n[bold magenta]═══ Step 1: Cleanup ═══[/bold magenta]")
    cleanup_results = cleanup_all(prefix, dry_run=False, skip_confirmation=True)

    # Step 2: Generate
    console.print("\n[bold magenta]═══ Step 2: Generate ═══[/bold magenta]")
    generate_results = generate_all(
        num_projects=num_projects,
        num_sequences=num_sequences,
        num_shots=num_shots,
        num_tasks=num_tasks,
        num_users=num_users,
        batch_size=batch_size,
        prefix=prefix,
    )

    # Display combined summary
    console.print("\n" + "=" * 60)
    console.print(Panel(
        "[bold green]✓ Reset and Generate Completed![/bold green]\n\n"
        f"[cyan]Cleanup Summary:[/cyan]\n"
        f"  AYON: {cleanup_results['ayon']['projects_deleted']} projects, {cleanup_results['ayon']['users_deleted']} users deleted\n"
        f"  Kitsu: {cleanup_results['kitsu']['projects_deleted']} projects, {cleanup_results['kitsu']['users_deleted']} users deleted\n\n"
        f"[cyan]Generation Summary:[/cyan]\n"
        f"  AYON: {len(generate_results['ayon'].get('data', {}).get('projects', []))} projects, "
        f"{len(generate_results['ayon'].get('data', {}).get('shots', []))} shots created\n"
        f"  Kitsu: {len(generate_results['kitsu'].get('data', {}).get('projects', []))} projects, "
        f"{len(generate_results['kitsu'].get('data', {}).get('shots', []))} shots created",
        title="🎉 Operation Complete",
        border_style="green"
    ))


if __name__ == "__main__":
    app()

