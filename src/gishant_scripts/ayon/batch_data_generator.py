"""Batch data generator for Ayon load testing.

This module provides utilities to generate synthetic test data for Ayon projects,
including projects, sequences, shots, users, and jobs. It's designed to simulate
realistic workloads for testing the Kafka-based sync architecture.
"""

import asyncio
import random
import string
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table

try:
    import ayon_api
except ImportError:
    ayon_api = None

# Import get_connection function directly to avoid circular imports
import os
from gishant_scripts.common.config import AppConfig


def get_connection():
    """Establish connection to Ayon server."""
    AppConfig()
    if ayon_api is None:
        raise RuntimeError("ayon-python-api not installed")
    server_url = os.getenv("AYON_SERVER_URL_LOCAL")
    api_key = os.getenv("AYON_API_KEY_LOCAL")
    if not server_url or not api_key:
        raise RuntimeError("AYON_SERVER_URL and AYON_API_KEY must be set")
    os.environ["AYON_SERVER_URL"] = server_url
    os.environ["AYON_API_KEY"] = api_key
    # ayon_api auto-initializes when env vars are set
    # Connection will be created on first API call
    return ayon_api


console = Console()


# ============================================================================
# Data Generation Utilities
# ============================================================================


def generate_random_string(length: int = 8, prefix: str = "") -> str:
    """Generate a random string."""
    chars = string.ascii_lowercase + string.digits
    random_part = "".join(random.choice(chars) for _ in range(length))
    return f"{prefix}{random_part}" if prefix else random_part


def generate_project_name(index: int, prefix: str = "test") -> tuple[str, str]:
    """Generate a project name and code using realistic conventions.

    Examples: "Bollywoof" -> "bwfro", "TestProject" -> "tstprj"
    """
    # Generate a realistic project name
    project_names = [
        "Bollywoof",
        "MysticRealm",
        "CyberCity",
        "NeonDreams",
        "ShadowRun",
        "StarQuest",
        "DarkMatter",
        "LightSpeed",
        "QuantumLeap",
        "CosmicDrift",
    ]
    # Use prefix if provided and not "test" (default)
    if prefix and prefix != "test":
        name = f"{prefix.capitalize()}Project{index:02d}"
    elif index <= len(project_names):
        name = project_names[index - 1]
    else:
        name = f"TestProject{index:02d}"

    # Generate code from name (first 2-3 letters of each word, lowercase)
    words = name.replace("Project", "").split()
    if len(words) == 1:
        code = words[0][:5].lower()
    else:
        code = "".join(word[:2].lower() for word in words[:3])

    return name, code


def generate_episode_name(index: int) -> str:
    """Generate an episode name using EP## convention."""
    return f"EP{index:02d}"


def generate_sequence_name(project_code: str, episode_index: int, sequence_index: int) -> str:
    """Generate a sequence name using project_code_episode_sequence convention.

    Example: "bwfro_02_0240" for project "bwfro", episode 2, sequence 240
    """
    return f"{project_code}_{episode_index:02d}_{sequence_index:04d}"


def generate_shot_name(sequence_name: str, shot_index: int) -> str:
    """Generate a shot name using sequence_name_#### convention.

    Example: "bwfro_02_0240_0000", "bwfro_02_0240_0010"
    """
    return f"{sequence_name}_{shot_index:04d}"


def generate_user_name(index: int, prefix: str = "testuser") -> str:
    """Generate a user name."""
    return f"{prefix}_{index:03d}"


# ============================================================================
# Ayon Data Creation Functions
# ============================================================================


def create_project(api: Any, name: str, code: str) -> dict[str, Any] | None:
    """Create a project in Ayon."""
    try:
        api.create_project(name, code)
        return {"name": name, "code": code, "status": "created"}
    except Exception as e:
        console.print(f"[red]Error creating project {name}: {e}[/red]")
        return None


def create_folder(api: Any, project_name: str, folder_name: str, folder_type: str = "Folder") -> dict[str, Any] | None:
    """Create a folder (sequence/shot) in Ayon."""
    try:
        folder_data = {
            "name": folder_name,
            "folderType": folder_type,
            "parent": None,  # Top-level folder
        }
        api.post(f"projects/{project_name}/folders", **folder_data)
        # Ayon may normalize folder names, so fetch the actual created folder to get its real name
        time.sleep(0.1)  # Small delay to ensure folder is created
        try:
            created_folders = list(api.get_folders(project_name, folder_names=[folder_name]))
            if created_folders:
                actual_name = created_folders[0].get("name", folder_name)
                return {"name": actual_name, "type": folder_type, "status": "created", "project": project_name}
        except Exception:
            pass
        return {"name": folder_name, "type": folder_type, "status": "created", "project": project_name}
    except Exception as e:
        console.print(f"[red]Error creating folder {folder_name} in {project_name}: {e}[/red]")
        return None


def create_task(
    api: Any, project_name: str, folder_name: str, task_name: str, task_type: str = "Animation"
) -> dict[str, Any] | None:
    """Create a task in Ayon."""
    try:
        # First, try to get folder by path (most reliable)
        folder = None
        try:
            folder = api.get_folder_by_path(project_name, folder_name)
        except Exception:
            pass

        # If not found by path, try by name (case-insensitive search)
        if not folder:
            # Try exact match first
            folders = list(api.get_folders(project_name, folder_names=[folder_name]))
            if not folders:
                # Try case-insensitive by searching all folders
                all_folders = list(api.get_folders(project_name))
                for f in all_folders:
                    if f.get("name", "").lower() == folder_name.lower():
                        folder = f
                        break
            else:
                folder = folders[0]

        if not folder:
            # Debug: list available folders
            try:
                all_folders_debug = list(api.get_folders(project_name, folder_types=["Shot"]))
                folder_names_debug = [f.get("name") for f in all_folders_debug]
                console.print(
                    f"[yellow]Debug: Available shot folders in '{project_name}': {folder_names_debug[:5]}[/yellow]"
                )
            except Exception:
                pass
            console.print(f"[red]Error: Folder '{folder_name}' not found in project '{project_name}'[/red]")
            return None

        folder_id = folder["id"]

        # Use the proper API method to create task
        task_id = api.create_task(
            project_name=project_name,
            name=task_name,
            task_type=task_type,
            folder_id=folder_id,
        )
        return {"name": task_name, "type": task_type, "status": "created", "id": task_id}
    except Exception as e:
        console.print(f"[red]Error creating task {task_name} in {project_name}/{folder_name}: {e}[/red]")
        import traceback

        console.print(f"[dim]{traceback.format_exc()}[/dim]")
        return None


def create_user(api: Any, username: str, full_name: str, email: str) -> dict[str, Any] | None:
    """Create a user in Ayon."""
    try:
        user_data = {
            "name": username,
            "attrib": {
                "fullName": full_name,
                "email": email,
            },
        }
        api.post("users", **user_data)
        return {"name": username, "status": "created"}
    except Exception as e:
        console.print(f"[red]Error creating user {username}: {e}[/red]")
        return None


# ============================================================================
# Batch Processing Functions
# ============================================================================


def process_batch(
    api: Any,
    batch_items: list[dict[str, Any]],
    operation: str,
    progress: Progress,
    task_id: Any,
) -> list[dict[str, Any]]:
    """Process a batch of items."""
    results = []
    for item in batch_items:
        try:
            if operation == "project":
                result = create_project(api, item["name"], item["code"])
            elif operation == "sequence":
                result = create_folder(api, item["project"], item["name"], "Sequence")
            elif operation == "shot":
                result = create_folder(api, item["project"], item["name"], "Shot")
            elif operation == "task":
                result = create_task(api, item["project"], item["folder"], item["name"], item.get("type", "Animation"))
            elif operation == "user":
                result = create_user(api, item["username"], item["full_name"], item["email"])
            else:
                result = None

            if result:
                results.append(result)
        except Exception as e:
            console.print(f"[red]Error processing {operation} item: {e}[/red]")

        progress.update(task_id, advance=1)

    return results


def generate_batch_data(
    api: Any,
    num_projects: int = 1,
    num_sequences_per_project: int = 5,
    num_shots_per_sequence: int = 10,
    num_tasks_per_shot: int = 3,
    num_users: int = 5,
    batch_size: int = 10,
    concurrency: int = 1,
    prefix: str = "test",
) -> dict[str, Any]:
    """Generate batch data for load testing."""
    results = {
        "projects": [],
        "sequences": [],
        "shots": [],
        "tasks": [],
        "users": [],
        "errors": [],
    }

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        # Generate projects
        if num_projects > 0:
            project_task = progress.add_task(f"[cyan]Creating {num_projects} projects...", total=num_projects)
            projects_data = [
                {"name": name, "code": code}
                for name, code in [generate_project_name(i, prefix) for i in range(1, num_projects + 1)]
            ]

            # Process projects in batches
            for i in range(0, len(projects_data), batch_size):
                batch = projects_data[i : i + batch_size]
                batch_results = process_batch(api, batch, "project", progress, project_task)
                results["projects"].extend(batch_results)
                time.sleep(0.1)  # Small delay to avoid overwhelming the API

        # Generate users
        if num_users > 0:
            user_task = progress.add_task(f"[cyan]Creating {num_users} users...", total=num_users)
            users_data = [
                {
                    "username": generate_user_name(i, prefix),
                    "full_name": f"Test User {i}",
                    "email": f"{prefix}user{i:03d}@test.local",
                }
                for i in range(1, num_users + 1)
            ]

            for i in range(0, len(users_data), batch_size):
                batch = users_data[i : i + batch_size]
                batch_results = process_batch(api, batch, "user", progress, user_task)
                results["users"].extend(batch_results)
                time.sleep(0.1)

        # Generate sequences, shots, and tasks for each project
        created_projects = results["projects"]
        if created_projects and (num_sequences_per_project > 0 or num_shots_per_sequence > 0):
            for project in created_projects:
                project_name = project["name"]
                project_code = project.get("code", project_name[:5].lower())

                # Generate episodes first (as sequences in Ayon)
                num_episodes = max(1, (num_sequences_per_project + 9) // 10)  # ~10 sequences per episode
                episodes = []
                for ep_idx in range(1, num_episodes + 1):
                    ep_name = generate_episode_name(ep_idx)
                    # Create episode as a sequence/folder in Ayon
                    ep_data = {"project": project_name, "name": ep_name}
                    try:
                        ep_result = create_folder(api, project_name, ep_name, "Sequence")
                        if ep_result:
                            episodes.append({"name": ep_name, "index": ep_idx})
                    except Exception as e:
                        console.print(f"[yellow]Warning: Could not create episode {ep_name}: {e}[/yellow]")

                # Generate sequences
                if num_sequences_per_project > 0:
                    seq_task = progress.add_task(
                        f"[cyan]Creating {num_sequences_per_project} sequences for {project_name}...",
                        total=num_sequences_per_project,
                    )
                    sequences_data = []
                    seq_idx = 0
                    for ep in episodes:
                        # Generate sequences for this episode
                        seqs_per_ep = num_sequences_per_project // num_episodes
                        for i in range(seqs_per_ep):
                            seq_idx += 1
                            if seq_idx > num_sequences_per_project:
                                break
                            seq_name = generate_sequence_name(project_code, ep["index"], seq_idx * 10)
                            sequences_data.append({"project": project_name, "name": seq_name})

                    for i in range(0, len(sequences_data), batch_size):
                        batch = sequences_data[i : i + batch_size]
                        batch_results = process_batch(api, batch, "sequence", progress, seq_task)
                        results["sequences"].extend(batch_results)
                        time.sleep(0.1)

                # Generate shots for each sequence
                created_sequences = [s["name"] for s in results["sequences"] if s.get("status") == "created"]
                if created_sequences and num_shots_per_sequence > 0:
                    shot_task = progress.add_task(
                        f"[cyan]Creating {num_shots_per_sequence * len(created_sequences)} shots...",
                        total=num_shots_per_sequence * len(created_sequences),
                    )
                    shots_data = []
                    for seq_name in created_sequences:
                        # Generate shots with frame numbers (0000, 0010, 0020, etc.)
                        for shot_idx in range(num_shots_per_sequence):
                            frame_number = shot_idx * 10  # 0000, 0010, 0020, etc.
                            shots_data.append(
                                {
                                    "project": project_name,
                                    "name": generate_shot_name(seq_name, frame_number),
                                }
                            )

                    for i in range(0, len(shots_data), batch_size):
                        batch = shots_data[i : i + batch_size]
                        batch_results = process_batch(api, batch, "shot", progress, shot_task)
                        results["shots"].extend(batch_results)
                        time.sleep(0.1)

                # Small delay to ensure folders are fully created before querying
                time.sleep(0.5)

                # Generate tasks for each shot
                project_shots = [
                    s for s in results["shots"] if s.get("status") == "created" and s.get("project") == project_name
                ]
                if project_shots and num_tasks_per_shot > 0:
                    task_types = ["Animation", "Compositing", "Lighting", "Rendering", "Modeling"]
                    task_task = progress.add_task(
                        f"[cyan]Creating {num_tasks_per_shot * len(project_shots)} tasks...",
                        total=num_tasks_per_shot * len(project_shots),
                    )
                    tasks_data = []
                    for shot in project_shots:
                        shot_name = shot["name"]
                        for task_idx in range(num_tasks_per_shot):
                            tasks_data.append(
                                {
                                    "project": project_name,
                                    "folder": shot_name,
                                    "name": random.choice(task_types),
                                    "type": random.choice(task_types),
                                }
                            )

                    for i in range(0, len(tasks_data), batch_size):
                        batch = tasks_data[i : i + batch_size]
                        batch_results = process_batch(api, batch, "task", progress, task_task)
                        results["tasks"].extend(batch_results)
                        time.sleep(0.1)

    return results


def cleanup_test_data(api: Any, prefix: str = "test", dry_run: bool = False) -> dict[str, Any]:
    """Clean up test data from AYON.

    Args:
        api: AYON API instance
        prefix: Prefix used for test data (default: "test")
        dry_run: If True, only show what would be deleted without actually deleting

    Returns:
        Dictionary with cleanup results
    """
    results = {
        "projects_deleted": 0,
        "users_deleted": 0,
        "errors": [],
    }

    try:
        # Get all projects
        all_projects = list(api.get_projects())
        if not all_projects:
            console.print("[yellow]No projects found[/yellow]")
        else:
            # Filter test projects by prefix
            test_projects = [p for p in all_projects if p.get("name", "").lower().startswith(prefix.lower())]

            if not test_projects:
                console.print(f"[yellow]No test projects found with prefix '{prefix}'[/yellow]")
            else:
                console.print(f"[cyan]Found {len(test_projects)} test projects to delete[/cyan]")

                if dry_run:
                    console.print("[yellow]Dry run mode - listing projects that would be deleted:[/yellow]")
                    for proj in test_projects:
                        console.print(f"  - {proj['name']} ({proj.get('code', 'N/A')})")
                else:
                    with Progress(
                        SpinnerColumn(),
                        TextColumn("[progress.description]{task.description}"),
                        BarColumn(),
                        TaskProgressColumn(),
                        console=console,
                    ) as progress:
                        task = progress.add_task("[red]Deleting projects...", total=len(test_projects))
                        for proj in test_projects:
                            try:
                                api.delete(f"projects/{proj['name']}")
                                results["projects_deleted"] += 1
                                progress.update(task, advance=1)
                            except Exception as e:
                                error_msg = f"Error deleting project {proj['name']}: {e}"
                                results["errors"].append(error_msg)
                                console.print(f"[red]{error_msg}[/red]")
                                progress.update(task, advance=1)

        # Get all users
        try:
            all_users = list(api.get_users())
            if not all_users:
                console.print("[yellow]No users found[/yellow]")
            else:
                # Filter test users by prefix in username or email
                test_users = [
                    u
                    for u in all_users
                    if (
                        (u.get("name") or "").lower().startswith(f"{prefix}")
                        or (u.get("attrib", {}).get("email") or "").startswith(f"{prefix}user")
                    )
                ]

                if not test_users:
                    console.print(f"[yellow]No test users found with prefix '{prefix}'[/yellow]")
                else:
                    console.print(f"[cyan]Found {len(test_users)} test users to delete[/cyan]")

                    if dry_run:
                        console.print("[yellow]Dry run mode - listing users that would be deleted:[/yellow]")
                        for user in test_users:
                            email = user.get("attrib", {}).get("email", "N/A")
                            console.print(f"  - {user.get('name', 'N/A')} ({email})")
                    else:
                        with Progress(
                            SpinnerColumn(),
                            TextColumn("[progress.description]{task.description}"),
                            BarColumn(),
                            TaskProgressColumn(),
                            console=console,
                        ) as progress:
                            task = progress.add_task("[red]Deleting users...", total=len(test_users))
                            for user in test_users:
                                try:
                                    api.delete(f"users/{user['name']}")
                                    results["users_deleted"] += 1
                                    progress.update(task, advance=1)
                                except Exception as e:
                                    error_msg = f"Error deleting user {user.get('name', 'unknown')}: {e}"
                                    results["errors"].append(error_msg)
                                    console.print(f"[red]{error_msg}[/red]")
                                    progress.update(task, advance=1)
        except Exception as e:
            console.print(f"[yellow]Warning: Could not process users: {e}[/yellow]")

    except Exception as e:
        error_msg = f"Error during cleanup: {e}"
        results["errors"].append(error_msg)
        console.print(f"[red]{error_msg}[/red]")

    return results


def simulate_concurrent_users(
    api: Any,
    num_users: int,
    operations_per_user: int,
    batch_size: int = 10,
) -> dict[str, Any]:
    """Simulate multiple users submitting jobs concurrently."""
    results = {
        "total_operations": num_users * operations_per_user,
        "successful": 0,
        "failed": 0,
        "duration": 0,
    }

    def user_worker(user_id: int):
        """Simulate a single user's workload."""
        user_results = {"successful": 0, "failed": 0}
        for i in range(operations_per_user):
            try:
                # Simulate creating a shot or task
                project_name = f"test_project_{random.randint(1, 10)}"
                shot_name = f"SH{random.randint(1, 100):03d}"
                task_name = random.choice(["Animation", "Compositing", "Lighting"])

                # This would trigger a transaction
                create_task(api, project_name, shot_name, task_name)
                user_results["successful"] += 1
            except Exception:
                user_results["failed"] += 1
            time.sleep(random.uniform(0.1, 0.5))  # Random delay to simulate real usage

        return user_results

    start_time = time.time()

    with ThreadPoolExecutor(max_workers=num_users) as executor:
        futures = [executor.submit(user_worker, user_id) for user_id in range(num_users)]
        for future in as_completed(futures):
            user_results = future.result()
            results["successful"] += user_results["successful"]
            results["failed"] += user_results["failed"]

    results["duration"] = float(time.time() - start_time)
    return results


# ============================================================================
# CLI Commands
# ============================================================================


def generate_data_cli(
    num_projects: int = typer.Option(1, "--projects", "-p", help="Number of projects to create"),
    num_sequences: int = typer.Option(5, "--sequences", "-s", help="Number of sequences per project"),
    num_shots: int = typer.Option(10, "--shots", help="Number of shots per sequence"),
    num_tasks: int = typer.Option(3, "--tasks", "-t", help="Number of tasks per shot"),
    num_users: int = typer.Option(5, "--users", "-u", help="Number of users to create"),
    batch_size: int = typer.Option(10, "--batch-size", "-b", help="Batch size for operations"),
    prefix: str = typer.Option("test", "--prefix", help="Prefix for generated names"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be created without actually creating"),
):
    """Generate batch test data for Ayon."""
    if ayon_api is None:
        console.print("[red]Error: ayon-python-api not installed.[/red]")
        raise typer.Exit(code=1)

    if dry_run:
        console.print("[yellow]Dry run mode - no data will be created[/yellow]")
        console.print(f"Would create:")
        console.print(f"  - {num_projects} projects")
        console.print(f"  - {num_sequences} sequences per project")
        console.print(f"  - {num_shots} shots per sequence")
        console.print(f"  - {num_tasks} tasks per shot")
        console.print(f"  - {num_users} users")
        return

    api = get_connection()
    console.print(f"[bold cyan]Generating Ayon test data...[/bold cyan]")
    console.print(
        f"Projects: {num_projects}, Sequences: {num_sequences}, Shots: {num_shots}, Tasks: {num_tasks}, Users: {num_users}"
    )

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

    # Display results
    table = Table(title="Generation Results")
    table.add_column("Type", style="cyan")
    table.add_column("Created", style="green")
    table.add_column("Failed", style="red")

    table.add_row("Projects", str(len(results["projects"])), str(num_projects - len(results["projects"])))
    table.add_row(
        "Sequences", str(len(results["sequences"])), str(num_projects * num_sequences - len(results["sequences"]))
    )
    table.add_row(
        "Shots", str(len(results["shots"])), str(num_projects * num_sequences * num_shots - len(results["shots"]))
    )
    table.add_row(
        "Tasks",
        str(len(results["tasks"])),
        str(num_projects * num_sequences * num_shots * num_tasks - len(results["tasks"])),
    )
    table.add_row("Users", str(len(results["users"])), str(num_users - len(results["users"])))

    console.print(table)


def simulate_load_cli(
    num_users: int = typer.Option(10, "--users", "-u", help="Number of concurrent users"),
    operations_per_user: int = typer.Option(50, "--operations", "-o", help="Operations per user"),
    batch_size: int = typer.Option(10, "--batch-size", "-b", help="Batch size"),
):
    """Simulate concurrent user load to stress-test the sync service."""
    if ayon_api is None:
        console.print("[red]Error: ayon-python-api not installed.[/red]")
        raise typer.Exit(code=1)

    try:
        api = get_connection()
    except Exception as e:
        console.print(f"[red]Error connecting to Ayon: {e}[/red]")
        raise typer.Exit(code=1)

    console.print(
        f"[bold cyan]Simulating {num_users} concurrent users with {operations_per_user} operations each...[/bold cyan]"
    )

    results = simulate_concurrent_users(api, num_users, operations_per_user, batch_size)

    console.print(f"\n[green]Load test completed![/green]")
    console.print(f"Total operations: {results['total_operations']}")
    console.print(f"Successful: {results['successful']}")
    console.print(f"Failed: {results['failed']}")
    console.print(f"Duration: {results['duration']:.2f} seconds")
    console.print(f"Throughput: {results['total_operations'] / results['duration']:.2f} ops/sec")


def cleanup_cli(
    prefix: str = typer.Option("test", "--prefix", help="Prefix for test data to clean up"),
    dry_run: bool = typer.Option(False, "--dry-run", help="Show what would be deleted without actually deleting"),
    confirm: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt"),
):
    """Clean up test data from AYON."""
    if ayon_api is None:
        console.print("[red]Error: ayon-python-api not installed.[/red]")
        raise typer.Exit(code=1)

    try:
        api = get_connection()
    except Exception as e:
        console.print(f"[red]Error connecting to AYON: {e}[/red]")
        raise typer.Exit(code=1)

    if not dry_run and not confirm:
        console.print(
            f"[bold yellow]WARNING: This will delete ALL projects and users with prefix '{prefix}'[/bold yellow]"
        )
        response = typer.confirm("Are you sure you want to continue?")
        if not response:
            console.print("[yellow]Cleanup cancelled.[/yellow]")
            return

    console.print(f"[bold cyan]Cleaning up AYON test data (prefix: {prefix})...[/bold cyan]")

    results = cleanup_test_data(api, prefix, dry_run)

    # Display results
    if dry_run:
        console.print("\n[yellow]Dry run completed - no data was deleted[/yellow]")
    else:
        table = Table(title="Cleanup Results")
        table.add_column("Type", style="cyan")
        table.add_column("Deleted", style="green")
        table.add_column("Errors", style="red")

        table.add_row(
            "Projects",
            str(results["projects_deleted"]),
            str(len([e for e in results["errors"] if "project" in e.lower()])),
        )
        table.add_row(
            "Users", str(results["users_deleted"]), str(len([e for e in results["errors"] if "user" in e.lower()]))
        )

        console.print(table)

        if results["errors"]:
            console.print(f"\n[yellow]Total errors: {len(results['errors'])}[/yellow]")


if __name__ == "__main__":
    app = typer.Typer()
    app.command("generate")(generate_data_cli)
    app.command("simulate-load")(simulate_load_cli)
    app.command("cleanup")(cleanup_cli)
    app()
