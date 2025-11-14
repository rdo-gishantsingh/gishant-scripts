"""Common utilities for working with Google Gemini AI."""

from __future__ import annotations

from google import genai
from rich.console import Console
from rich.prompt import Prompt

# Available Gemini models
AVAILABLE_MODELS = [
    "gemini-2.5-flash",
    "gemini-2.5-pro",
    "gemini-2.0-flash-exp",
]

DEFAULT_MODEL = "gemini-2.5-flash"


class GeminiClient:
    """Wrapper for Google Gemini AI client with common utilities."""

    def __init__(self, api_key: str, model: str = DEFAULT_MODEL):
        """Initialize the Gemini client.

        Args:
            api_key: Google AI API key
            model: Gemini model to use (default: gemini-2.5-flash)
        """
        self.client = genai.Client(api_key=api_key)
        self.model = model
        self.console = Console()

    def generate_content(self, prompt: str, *, show_progress: bool = True) -> str:
        """Generate content using Gemini AI.

        Args:
            prompt: The prompt to send to Gemini
            show_progress: Whether to show progress messages

        Returns:
            Generated content text

        Raises:
            ValueError: If response is empty
            Exception: For other API errors
        """
        if show_progress:
            self.console.print(f"[cyan]Generating content with {self.model}...[/cyan]")
            self.console.print("[dim]This may take 30-60 seconds...[/dim]")

        try:
            response = self.client.models.generate_content(
                model=self.model,
                contents=prompt,
            )

            if not response.text:
                raise ValueError("Empty response from Gemini API")

            return str(response.text)

        except Exception as e:
            self.console.print(f"[red]Error generating content: {e}[/red]")
            raise


def select_model_interactive(default: str = DEFAULT_MODEL) -> str:
    """Interactively select a Gemini model using Rich TUI.

    Displays available models and allows user to select one using arrow keys
    or by entering a number.

    Args:
        default: Default model to preselect

    Returns:
        Selected model name
    """
    console = Console()

    console.print("\n[bold cyan]Select Gemini Model:[/bold cyan]\n")

    # Display available models with numbers
    for idx, model in enumerate(AVAILABLE_MODELS, 1):
        default_marker = " [green](default)[/green]" if model == default else ""
        console.print(f"  [cyan]{idx}[/cyan]. {model}{default_marker}")

    console.print()

    # Get user selection
    while True:
        choice = Prompt.ask(
            "Enter model number or press Enter for default",
            default=str(AVAILABLE_MODELS.index(default) + 1),
            show_default=False,
        )

        try:
            choice_num = int(choice)
            if 1 <= choice_num <= len(AVAILABLE_MODELS):
                selected_model = AVAILABLE_MODELS[choice_num - 1]
                console.print(f"\n[green]✓ Selected: {selected_model}[/green]\n")
                return selected_model
            else:
                console.print(f"[red]Please enter a number between 1 and {len(AVAILABLE_MODELS)}[/red]")
        except ValueError:
            console.print(f"[red]Invalid input. Please enter a number between 1 and {len(AVAILABLE_MODELS)}[/red]")


def validate_model(model: str) -> str:
    """Validate and return a model name.

    Args:
        model: Model name to validate

    Returns:
        Validated model name

    Raises:
        ValueError: If model is not in available models
    """
    if model not in AVAILABLE_MODELS:
        raise ValueError(
            f"Invalid model '{model}'. Available models: {', '.join(AVAILABLE_MODELS)}"
        )
    return model
