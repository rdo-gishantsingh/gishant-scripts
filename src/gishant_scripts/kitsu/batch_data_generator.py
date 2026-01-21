"""Batch data generator for Kitsu load testing.

This module provides utilities to generate synthetic test data for Kitsu projects,
including projects, sequences, shots, users, and tasks. It's designed to simulate
realistic workloads for testing the Kafka-based sync architecture.
"""

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
    import gazu
except ImportError:
    gazu = None

# Import get_connection function directly to avoid circular imports
import os
from gishant_scripts.common.config import AppConfig


def get_connection():
    """Establish connection to Kitsu server."""
    AppConfig()
    if gazu is None:
        raise RuntimeError("gazu not installed")
    host = os.getenv("KITSU_API_URL_LOCAL") or os.getenv("KITSU_API_URL")
    api_key = os.getenv("KITSU_API_KEY_LOCAL") or os.getenv("KITSU_API_KEY")
    login = os.getenv("KITSU_LOGIN_LOCAL") or os.getenv("KITSU_LOGIN")
    password = os.getenv("KITSU_PASSWORD_LOCAL") or os.getenv("KITSU_PASSWORD")

    if not host:
        raise RuntimeError("KITSU_API_URL must be set")

    # Ensure host ends with /api if not already present
    if not host.endswith("/api"):
        if host.endswith("/"):
            host = host.rstrip("/") + "/api"
        else:
            host = host + "/api"

    gazu.set_host(host)

    # Verify host is valid
    if not gazu.client.host_is_valid():
        raise RuntimeError(f"Kitsu server `{host}` is not valid or not reachable")

    # Try token-based authentication first (preferred for bots/automation)
    if api_key:
        try:
            gazu.set_token(api_key)
            # Verify authentication by trying to get current user
            try:
                user = gazu.client.get_current_user()
                if user:
                    console.print(
                        f"[green]Authenticated to Kitsu using API token (user: {user.get('email', 'unknown')})[/green]"
                    )
                    return gazu
            except Exception as e:
                console.print(f"[yellow]Warning: Token set but verification failed: {e}[/yellow]")
                # Token might still work, continue anyway
                console.print("[green]Authenticated to Kitsu using API token[/green]")
                return gazu
        except Exception as e:
            console.print(f"[yellow]Warning: Token authentication failed: {e}[/yellow]")
            if login and password:
                console.print("[yellow]Falling back to login/password authentication...[/yellow]")
            else:
                raise RuntimeError(f"Token authentication failed and no login credentials provided: {e}")

    # Fall back to login/password authentication
    if login and password:
        try:
            gazu.log_in(login, password)
            # Verify authentication
            try:
                user = gazu.client.get_current_user()
                if user:
                    console.print(
                        f"[green]Authenticated to Kitsu using login/password (user: {user.get('email', login)})[/green]"
                    )
                else:
                    console.print("[green]Authenticated to Kitsu using login/password[/green]")
            except Exception:
                console.print("[green]Authenticated to Kitsu using login/password[/green]")
            return gazu
        except Exception as e:
            error_msg = str(e)
            if "405" in error_msg or "MethodNotAllowed" in error_msg:
                raise RuntimeError(
                    f"Kitsu server does not support login endpoint. "
                    f"Please use KITSU_API_KEY for token-based authentication instead. "
                    f"Error: {e}"
                )
            raise RuntimeError(f"Failed to authenticate to Kitsu: {e}")
    else:
        raise RuntimeError("KITSU_API_KEY or KITSU_LOGIN/KITSU_PASSWORD must be set")


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
    if index <= len(project_names):
        name = project_names[index - 1]
    else:
        name = f"{prefix.capitalize()}Project{index:02d}"

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
# Kitsu Data Creation Functions
# ============================================================================


def create_project(name: str, code: str) -> dict[str, Any] | None:
    """Create a project in Kitsu."""
    try:
        project = gazu.project.new_project(name, code)
        if project is None:
            console.print(f"[red]Error creating project {name}: gazu returned None[/red]")
            return None
        return {"id": project["id"], "name": name, "code": code, "status": "created"}
    except Exception as e:
        console.print(f"[red]Error creating project {name}: {e}[/red]")
        return None


def create_sequence(project_id: str, sequence_name: str) -> dict[str, Any] | None:
    """Create a sequence in Kitsu."""
    try:
        sequence = gazu.shot.new_sequence(project_id, {"name": sequence_name})
        if sequence is None:
            console.print(f"[red]Error creating sequence {sequence_name}: gazu returned None[/red]")
            return None
        return {"id": sequence["id"], "name": sequence_name, "status": "created"}
    except Exception as e:
        console.print(f"[red]Error creating sequence {sequence_name}: {e}[/red]")
        return None


def create_shot(project_id: str, sequence_id: str, shot_name: str) -> dict[str, Any] | None:
    """Create a shot in Kitsu."""
    try:
        shot = gazu.shot.new_shot(project_id, sequence_id, {"name": shot_name})
        if shot is None:
            console.print(f"[red]Error creating shot {shot_name}: gazu returned None[/red]")
            return None
        return {"id": shot["id"], "name": shot_name, "status": "created"}
    except Exception as e:
        console.print(f"[red]Error creating shot {shot_name}: {e}[/red]")
        return None


def create_task(
    project_id: str, entity_id: str, task_type_id: str, person_id: str | None = None
) -> dict[str, Any] | None:
    """Create a task in Kitsu.

    Args:
        project_id: Project ID
        entity_id: Entity (shot/asset) ID
        task_type_id: Task type ID
        person_id: Optional person ID to assign as assigner
    """
    try:
        # gazu.task.new_task requires entity dict and task_type dict, not IDs
        # First, get the entity (shot)
        entity = gazu.shot.get_shot(entity_id)
        if entity is None:
            # Try as asset if shot lookup fails
            entity = gazu.asset.get_asset(entity_id)
        if entity is None:
            console.print(f"[red]Error creating task: Entity {entity_id} not found[/red]")
            return None

        # Get task type dict
        task_type = gazu.task.get_task_type(task_type_id)
        if task_type is None:
            console.print(f"[red]Error creating task: Task type {task_type_id} not found[/red]")
            return None

        # Get assigner if person_id provided
        assigner = None
        if person_id:
            assigner = gazu.person.get_person(person_id)
            if assigner is None:
                console.print(f"[yellow]Warning: Person {person_id} not found, creating task without assigner[/yellow]")

        task = gazu.task.new_task(entity, task_type, assigner=assigner)
        if task is None:
            console.print(f"[red]Error creating task: gazu returned None[/red]")
            return None

        # Ensure task is a dict before accessing keys
        if not isinstance(task, dict):
            console.print(f"[red]Error creating task: unexpected return type {type(task)}[/red]")
            return None

        return {"id": task["id"], "status": "created"}
    except Exception as e:
        error_msg = str(e)
        # Check if task already exists (common error)
        # The error ('data/tasks', True) indicates a ParameterException, often due to duplicate tasks
        if "already exists" in error_msg.lower() or "duplicate" in error_msg.lower() or "('data/tasks'" in error_msg:
            console.print(f"[yellow]Task already exists for entity {entity_id}, skipping creation[/yellow]")
            return None
        console.print(f"[red]Error creating task for entity {entity_id}: {e}[/red]")
        return None


def create_person(username: str, email: str, first_name: str = "", last_name: str = "") -> dict[str, Any] | None:
    """Create a person (user) in Kitsu.

    Args:
        username: Username for the person
        email: Email address (required)
        first_name: First name (defaults to username if not provided)
        last_name: Last name (defaults to empty string if not provided)
    """
    try:
        # gazu.person.new_person requires positional args: first_name, last_name, email
        first_name = first_name or (username.split("_")[0] if "_" in username else username)
        last_name = last_name or (username.split("_")[1] if "_" in username and len(username.split("_")) > 1 else "")

        # Check if person already exists by email
        try:
            existing_person = gazu.person.get_person_by_email(email)
            if existing_person is not None:
                console.print(f"[yellow]Person with email {email} already exists, skipping creation[/yellow]")
                return {"id": existing_person["id"], "name": username, "status": "exists"}
        except Exception:
            # Person doesn't exist, continue with creation
            pass

        person = gazu.person.new_person(first_name, last_name, email)
        if person is None:
            console.print(f"[red]Error creating person {username}: gazu returned None[/red]")
            return None

        # Ensure person is a dict before accessing keys
        if not isinstance(person, dict):
            console.print(f"[red]Error creating person {username}: unexpected return type {type(person)}[/red]")
            return None

        return {"id": person["id"], "name": username, "status": "created"}
    except Exception as e:
        error_msg = str(e)
        # Handle ParameterException which might indicate validation error or existing person
        if "ParameterException" in str(type(e).__name__) or "('data/persons'" in error_msg:
            # Try to get existing person one more time
            try:
                existing_person = gazu.person.get_person_by_email(email)
                if existing_person is not None:
                    console.print(
                        f"[yellow]Person with email {email} already exists (detected via error), skipping creation[/yellow]"
                    )
                    return {"id": existing_person["id"], "name": username, "status": "exists"}
            except Exception:
                pass
            console.print(
                f"[red]Error creating person {username}: Server validation error - person may already exist or have invalid data[/red]"
            )
        else:
            console.print(f"[red]Error creating person {username}: {e}[/red]")
        return None


# ============================================================================
# Batch Processing Functions
# ============================================================================


def process_batch(
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
                result = create_project(item["name"], item["code"])
            elif operation == "sequence":
                result = create_sequence(item["project_id"], item["name"])
            elif operation == "shot":
                result = create_shot(item["project_id"], item["sequence_id"], item["name"])
            elif operation == "task":
                result = create_task(item["project_id"], item["entity_id"], item["task_type_id"], item.get("person_id"))
            elif operation == "person":
                result = create_person(
                    item["username"], item["email"], item.get("first_name", ""), item.get("last_name", "")
                )
            else:
                result = None

            if result:
                results.append(result)
        except Exception as e:
            console.print(f"[red]Error processing {operation} item: {e}[/red]")

        progress.update(task_id, advance=1)

    return results


def get_or_create_task_type(task_type_name: str) -> str | None:
    """Get or create a task type in Kitsu."""
    try:
        task_types = gazu.task.all_task_types()
        for task_type in task_types:
            if task_type["name"] == task_type_name:
                return task_type["id"]

        # Create if not found
        task_type = gazu.task.new_task_type({"name": task_type_name})
        return task_type["id"]
    except Exception as e:
        console.print(f"[red]Error getting/creating task type {task_type_name}: {e}[/red]")
        return None


def generate_batch_data(
    num_projects: int = 1,
    num_sequences_per_project: int = 5,
    num_shots_per_sequence: int = 10,
    num_tasks_per_shot: int = 3,
    num_users: int = 5,
    batch_size: int = 10,
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

    # Get or create task types
    task_types = ["Animation", "Compositing", "Lighting", "Rendering", "Modeling"]
    task_type_ids = {}
    for task_type_name in task_types:
        task_type_id = get_or_create_task_type(task_type_name)
        if task_type_id:
            task_type_ids[task_type_name] = task_type_id

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

            for i in range(0, len(projects_data), batch_size):
                batch = projects_data[i : i + batch_size]
                batch_results = process_batch(batch, "project", progress, project_task)
                results["projects"].extend(batch_results)
                time.sleep(0.1)

        # Generate users (persons)
        if num_users > 0:
            user_task = progress.add_task(f"[cyan]Creating {num_users} users...", total=num_users)
            users_data = [
                {
                    "username": generate_user_name(i, prefix),
                    "email": f"{prefix}user{i:03d}@test.local",
                    "first_name": f"Test",
                    "last_name": f"User {i}",
                }
                for i in range(1, num_users + 1)
            ]

            for i in range(0, len(users_data), batch_size):
                batch = users_data[i : i + batch_size]
                batch_results = process_batch(batch, "person", progress, user_task)
                results["users"].extend(batch_results)
                time.sleep(0.1)

        # Generate sequences, shots, and tasks for each project
        created_projects = results["projects"]
        if created_projects and (num_sequences_per_project > 0 or num_shots_per_sequence > 0):
            for project in created_projects:
                project_id = project["id"]
                project_name = project["name"]

                # Generate episodes first (if needed)
                num_episodes = max(1, (num_sequences_per_project + 9) // 10)  # ~10 sequences per episode
                episodes = []
                for ep_idx in range(1, num_episodes + 1):
                    ep_name = generate_episode_name(ep_idx)
                    # Create episode as a sequence in Kitsu
                    try:
                        ep_seq = gazu.shot.new_sequence(project_id, {"name": ep_name})
                        if ep_seq is None:
                            console.print(
                                f"[yellow]Warning: Could not create episode {ep_name}: gazu returned None[/yellow]"
                            )
                        else:
                            episodes.append({"id": ep_seq["id"], "name": ep_name, "index": ep_idx})
                    except Exception as e:
                        console.print(f"[yellow]Warning: Could not create episode {ep_name}: {e}[/yellow]")

                # Generate sequences
                if num_sequences_per_project > 0:
                    seq_task = progress.add_task(
                        f"[cyan]Creating {num_sequences_per_project} sequences for {project_name}...",
                        total=num_sequences_per_project,
                    )
                    project_code = project.get("code", project_name[:5].lower())
                    sequences_data = []
                    seq_idx = 0
                    for ep in episodes:
                        # Generate sequences for this episode
                        seqs_per_ep = num_sequences_per_project // num_episodes
                        for i in range(seqs_per_ep):
                            seq_idx += 1
                            if seq_idx > num_sequences_per_project:
                                break
                            # Generate sequence number (0240, 0250, etc.)
                            seq_number = seq_idx * 10
                            seq_name = generate_sequence_name(project_code, ep["index"], seq_number)
                            sequences_data.append({"project_id": project_id, "name": seq_name, "episode_id": ep["id"]})

                    for i in range(0, len(sequences_data), batch_size):
                        batch = sequences_data[i : i + batch_size]
                        batch_results = process_batch(batch, "sequence", progress, seq_task)
                        results["sequences"].extend(batch_results)
                        time.sleep(0.1)

                # Generate shots for each sequence
                project_sequences = [s for s in results["sequences"] if s.get("status") == "created"]
                if project_sequences and num_shots_per_sequence > 0:
                    shot_task = progress.add_task(
                        f"[cyan]Creating {num_shots_per_sequence * len(project_sequences)} shots...",
                        total=num_shots_per_sequence * len(project_sequences),
                    )
                    shots_data = []
                    for seq in project_sequences:
                        seq_id = seq["id"]
                        seq_name = seq["name"]
                        # Generate shots with frame numbers (0000, 0010, 0020, etc.)
                        for shot_idx in range(num_shots_per_sequence):
                            frame_number = shot_idx * 10  # 0000, 0010, 0020, etc.
                            shots_data.append(
                                {
                                    "project_id": project_id,
                                    "sequence_id": seq_id,
                                    "name": generate_shot_name(seq_name, frame_number),
                                }
                            )

                    for i in range(0, len(shots_data), batch_size):
                        batch = shots_data[i : i + batch_size]
                        batch_results = process_batch(batch, "shot", progress, shot_task)
                        results["shots"].extend(batch_results)
                        time.sleep(0.1)

                # Generate tasks for each shot
                # Filter shots that were successfully created (they don't have project_id in result, so just check status)
                project_shots = [s for s in results["shots"] if s.get("status") == "created"]
                if project_shots and num_tasks_per_shot > 0 and task_type_ids:
                    task_task = progress.add_task(
                        f"[cyan]Creating {num_tasks_per_shot * len(project_shots)} tasks...",
                        total=num_tasks_per_shot * len(project_shots),
                    )
                    tasks_data = []
                    user_ids = [u["id"] for u in results["users"] if u.get("status") == "created"]

                    for shot in project_shots:
                        shot_id = shot["id"]
                        for _ in range(num_tasks_per_shot):
                            task_type_name = random.choice(list(task_type_ids.keys()))
                            tasks_data.append(
                                {
                                    "project_id": project_id,
                                    "entity_id": shot_id,
                                    "task_type_id": task_type_ids[task_type_name],
                                    "person_id": random.choice(user_ids) if user_ids else None,
                                }
                            )

                    for i in range(0, len(tasks_data), batch_size):
                        batch = tasks_data[i : i + batch_size]
                        batch_results = process_batch(batch, "task", progress, task_task)
                        results["tasks"].extend(batch_results)
                        time.sleep(0.1)

    return results


def cleanup_test_data(prefix: str = "test", dry_run: bool = False) -> dict[str, Any]:
    """Clean up test data from Kitsu.

    Args:
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
        all_projects = gazu.project.all_projects()
        if all_projects is None:
            console.print("[yellow]Warning: Could not fetch projects[/yellow]")
            return results

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
                            gazu.project.remove_project(proj["id"])
                            results["projects_deleted"] += 1
                            progress.update(task, advance=1)
                        except Exception as e:
                            error_msg = f"Error deleting project {proj['name']}: {e}"
                            results["errors"].append(error_msg)
                            console.print(f"[red]{error_msg}[/red]")
                            progress.update(task, advance=1)

        # Get all persons/users
        try:
            all_persons = gazu.person.all_persons()
            if all_persons is None:
                console.print("[yellow]Warning: Could not fetch persons[/yellow]")
            else:
                # Filter test users by prefix in email or first_name
                test_persons = [
                    p
                    for p in all_persons
                    if (
                        p.get("email", "").startswith(f"{prefix}user")
                        or p.get("first_name", "").lower() == prefix.lower()
                    )
                ]

                if not test_persons:
                    console.print(f"[yellow]No test users found with prefix '{prefix}'[/yellow]")
                else:
                    console.print(f"[cyan]Found {len(test_persons)} test users to delete[/cyan]")

                    if dry_run:
                        console.print("[yellow]Dry run mode - listing users that would be deleted:[/yellow]")
                        for person in test_persons:
                            console.print(
                                f"  - {person.get('email', 'N/A')} ({person.get('first_name', '')} {person.get('last_name', '')})"
                            )
                    else:
                        with Progress(
                            SpinnerColumn(),
                            TextColumn("[progress.description]{task.description}"),
                            BarColumn(),
                            TaskProgressColumn(),
                            console=console,
                        ) as progress:
                            task = progress.add_task("[red]Deleting users...", total=len(test_persons))
                            for person in test_persons:
                                try:
                                    gazu.person.remove_person(person["id"])
                                    results["users_deleted"] += 1
                                    progress.update(task, advance=1)
                                except Exception as e:
                                    error_msg = f"Error deleting user {person.get('email', 'unknown')}: {e}"
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
    num_users: int,
    operations_per_user: int,
    batch_size: int = 10,
) -> dict[str, Any]:
    """Simulate multiple users submitting jobs concurrently."""
    results: dict[str, Any] = {
        "total_operations": num_users * operations_per_user,
        "successful": 0,
        "failed": 0,
        "duration": 0.0,
    }

    # Get existing projects and task types
    try:
        projects = gazu.project.all_open_projects()
        task_types = gazu.task.all_task_types()
        if projects is None or task_types is None:
            console.print("[red]Error: Failed to fetch projects or task types from Kitsu[/red]")
            return results
        if not projects or not task_types:
            console.print("[red]Error: Need at least one project and task type for load testing[/red]")
            return results
    except Exception as e:
        console.print(f"[red]Error fetching projects/task types: {e}[/red]")
        return results

    def user_worker(user_id: int):
        """Simulate a single user's workload."""
        user_results = {"successful": 0, "failed": 0}
        for i in range(operations_per_user):
            try:
                # Randomly select project and shot
                project = random.choice(projects)
                if project is None:
                    user_results["failed"] += 1
                    continue
                project_id = project.get("id")
                if not project_id:
                    user_results["failed"] += 1
                    continue

                # Get shots for this project
                shots = gazu.shot.all_shots_for_project(project_id)
                if shots is None or not shots:
                    user_results["failed"] += 1
                    continue

                shot = random.choice(shots)
                if shot is None:
                    user_results["failed"] += 1
                    continue
                shot_id = shot.get("id")
                if not shot_id:
                    user_results["failed"] += 1
                    continue

                # Create a task (this triggers sync)
                task_type = random.choice(task_types)
                if task_type is None or not task_type.get("id"):
                    user_results["failed"] += 1
                    continue
                create_task(project_id, shot_id, task_type["id"])
                user_results["successful"] += 1
            except Exception:
                user_results["failed"] += 1
            time.sleep(random.uniform(0.1, 0.5))

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
    """Generate batch test data for Kitsu."""
    if gazu is None:
        console.print("[red]Error: gazu not installed.[/red]")
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

    get_connection()
    console.print(f"[bold cyan]Generating Kitsu test data...[/bold cyan]")
    console.print(
        f"Projects: {num_projects}, Sequences: {num_sequences}, Shots: {num_shots}, Tasks: {num_tasks}, Users: {num_users}"
    )

    results = generate_batch_data(
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
    if gazu is None:
        console.print("[red]Error: gazu not installed.[/red]")
        raise typer.Exit(code=1)

    try:
        get_connection()
    except Exception as e:
        console.print(f"[red]Error connecting to Kitsu: {e}[/red]")
        raise typer.Exit(code=1)

    console.print(
        f"[bold cyan]Simulating {num_users} concurrent users with {operations_per_user} operations each...[/bold cyan]"
    )

    results = simulate_concurrent_users(num_users, operations_per_user, batch_size)

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
    """Clean up test data from Kitsu."""
    if gazu is None:
        console.print("[red]Error: gazu not installed.[/red]")
        raise typer.Exit(code=1)

    try:
        get_connection()
    except Exception as e:
        console.print(f"[red]Error connecting to Kitsu: {e}[/red]")
        raise typer.Exit(code=1)

    if not dry_run and not confirm:
        console.print(
            f"[bold yellow]WARNING: This will delete ALL projects and users with prefix '{prefix}'[/bold yellow]"
        )
        response = typer.confirm("Are you sure you want to continue?")
        if not response:
            console.print("[yellow]Cleanup cancelled.[/yellow]")
            return

    console.print(f"[bold cyan]Cleaning up Kitsu test data (prefix: {prefix})...[/bold cyan]")

    results = cleanup_test_data(prefix, dry_run)

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
            "Users",
            str(results["users_deleted"]),
            str(len([e for e in results["errors"] if "user" in e.lower() or "person" in e.lower()])),
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
