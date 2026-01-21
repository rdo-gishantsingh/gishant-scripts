import ayon_api
import os
import argparse
from rich.progress import BarColumn, Progress, SpinnerColumn, TextColumn, TaskProgressColumn
from rich.console import Console

console = Console()


def set_connection():
    """Connect to the Ayon API and returns the session object.

    Returns:
        ayon_api._api.GlobalServerAPI: Ayon connection

    """
    os.environ["AYON_SERVER_URL"] = "http://10.1.64.128/"
    os.environ["AYON_API_KEY"] = "cf939d4d8fe44909afbb40a10660c5e4"
    return ayon_api.get_server_api_connection()


ayon_connection = set_connection()


def test_ayon_connection():
    """Test Ayon connection by getting project root."""
    try:
        ayon_api.get_project_roots_by_platform("Bollywoof", "linux")
    except Exception as err:
        raise err


def main():
    """Main function to run stress test."""
    parser = argparse.ArgumentParser(
        description="Stress test Ayon connection",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "-n",
        "--iterations",
        type=int,
        default=1,
        help="Number of iterations to run (default: 1)",
    )
    args = parser.parse_args()

    iterations = args.iterations
    successful = 0
    failed = 0
    errors = []

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TaskProgressColumn(),
        console=console,
    ) as progress:
        task = progress.add_task(
            f"Testing Ayon connection (0/{iterations})...",
            total=iterations,
        )

        for i in range(iterations):
            progress.update(
                task,
                description=f"Testing Ayon connection ({i + 1}/{iterations})...",
            )
            try:
                test_ayon_connection()
                successful += 1
            except Exception as err:
                failed += 1
                error_msg = str(err)
                errors.append((i + 1, error_msg))
                console.print(f"[red]✗ Iteration {i + 1} failed: {error_msg}[/red]")

            progress.update(task, advance=1)

    # Print summary
    console.print("\n[bold]Test Summary:[/bold]")
    console.print(f"  Total iterations: {iterations}")
    console.print(f"  [green]Successful: {successful}[/green]")
    console.print(f"  [red]Failed: {failed}[/red]")
    if successful > 0:
        success_rate = (successful / iterations) * 100
        console.print(f"  Success rate: {success_rate:.1f}%")

    if errors:
        console.print("\n[bold red]Errors encountered:[/bold red]")
        for iteration, error in errors:
            console.print(f"  Iteration {iteration}: {error}")

    # Exit with error code if any failures
    if failed > 0:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
