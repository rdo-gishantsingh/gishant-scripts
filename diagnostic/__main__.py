"""Allow ``python -m diagnostic`` to invoke the Typer app.

This mirrors the ``dcc-run`` console script declared in ``pyproject.toml`` and
lets the diagnostic dispatcher be launched without a venv-installed entry point.
"""

from __future__ import annotations

from diagnostic.cli import app

if __name__ == "__main__":
    app()
