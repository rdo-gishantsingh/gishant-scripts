"""Main entry point for AYON CLI."""

import importlib.util
from pathlib import Path

# Import cli.py explicitly (not the cli/ package)
# We need to do this because we have both cli.py and cli/ directory
cli_path = Path(__file__).parent / "cli.py"
spec = importlib.util.spec_from_file_location("gishant_scripts.ayon.cli_module", cli_path)
cli_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli_module)

if __name__ == "__main__":
    cli_module.app()
