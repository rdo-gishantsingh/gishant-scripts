"""Common utilities for working with Google Gemini AI."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from google import genai
from rich.console import Console
from rich.prompt import Prompt


class GeminiModel(Enum):
    """Available Gemini models with pricing (input, output per million tokens)."""

    GEMINI_3_PRO_PREVIEW = ("gemini-3-pro-preview", 2.00, 12.00)
    GEMINI_3_FLASH_PREVIEW = ("gemini-3-flash-preview", 0.30, 2.50)
    GEMINI_2_5_FLASH = ("gemini-2.5-flash", 0.30, 2.50)
    GEMINI_2_5_PRO = ("gemini-2.5-pro", 1.25, 10.00)
    GEMINI_2_0_FLASH_EXP = ("gemini-2.0-flash-exp", 0.075, 0.30)

    def __init__(self, model_name: str, input_price: float, output_price: float) -> None:
        self.model_name = model_name
        self.input_price = input_price
        self.output_price = output_price


DEFAULT_MODEL = GeminiModel.GEMINI_3_PRO_PREVIEW


@dataclass
class UsageStats:
    """Token usage and cost stats for a single call or session."""

    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0
    input_cost: float = 0.0
    output_cost: float = 0.0
    total_cost: float = 0.0


class GeminiClient:
    """Wrapper for Google Gemini AI client with common utilities."""

    def __init__(self, api_key: str, model: GeminiModel | str = DEFAULT_MODEL):
        """Initialize the Gemini client.

        Args:
            api_key: Google AI API key
            model: Gemini model to use (enum or model name string)
        """
        self._model = validate_model(model) if isinstance(model, str) else model
        self.client = genai.Client(api_key=api_key)
        self.console = Console()
        self._session_usage: UsageStats = UsageStats()
        self._last_usage: UsageStats | None = None
        self._call_count: int = 0

    @property
    def model(self) -> GeminiModel:
        """Current Gemini model."""
        return self._model

    def _calculate_cost(self, prompt_tokens: int, completion_tokens: int) -> tuple[float, float]:
        """Calculate input and output costs based on model pricing."""
        input_cost = (prompt_tokens / 1_000_000) * self._model.input_price
        output_cost = (completion_tokens / 1_000_000) * self._model.output_price
        return (input_cost, output_cost)

    def generate_content(self, prompt: str, *, show_progress: bool = True, show_usage: bool = False) -> str:
        """Generate content using Gemini AI.

        Args:
            prompt: The prompt to send to Gemini
            show_progress: Whether to print progress messages (set False when caller
                provides its own progress, e.g. Rich Live TUI with spinner)
            show_usage: Whether to print token/cost summary after the call

        Returns:
            Generated content text

        Raises:
            ValueError: If response is empty
            Exception: For other API errors
        """
        if show_progress:
            self.console.print(f"[cyan]Generating content with {self._model.model_name}...[/cyan]")
            self.console.print("[dim]This may take 30-60 seconds...[/dim]")

        try:
            response = self.client.models.generate_content(
                model=self._model.model_name,
                contents=prompt,
            )

            if not response.text:
                raise ValueError("Empty response from Gemini API")

            usage = getattr(response, "usage_metadata", None)
            if usage is not None:
                prompt_tokens = getattr(usage, "prompt_token_count", 0) or 0
                completion_tokens = getattr(usage, "candidates_token_count", 0) or 0
                total_tokens = getattr(usage, "total_token_count", 0) or (prompt_tokens + completion_tokens)
                input_cost, output_cost = self._calculate_cost(prompt_tokens, completion_tokens)
                total_cost = input_cost + output_cost

                last = UsageStats(
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    total_tokens=total_tokens,
                    input_cost=input_cost,
                    output_cost=output_cost,
                    total_cost=total_cost,
                )
                self._last_usage = last
                self._session_usage.prompt_tokens += prompt_tokens
                self._session_usage.completion_tokens += completion_tokens
                self._session_usage.total_tokens += total_tokens
                self._session_usage.input_cost += input_cost
                self._session_usage.output_cost += output_cost
                self._session_usage.total_cost += total_cost
                self._call_count += 1

                if show_usage:
                    self.console.print(
                        f"[dim]Tokens: {prompt_tokens} in / {completion_tokens} out / {total_tokens} total[/dim]"
                    )
                    self.console.print(
                        f"[dim]Cost: ${input_cost:.6f} in / ${output_cost:.6f} out / ${total_cost:.6f} total[/dim]"
                    )

            return str(response.text)

        except Exception as e:
            self.console.print(f"[red]Error generating content: {e}[/red]")
            raise

    def get_last_usage(self) -> UsageStats | None:
        """Return usage stats from the last API call, or None if no call yet."""
        return self._last_usage

    def get_session_usage(self) -> UsageStats:
        """Return cumulative usage stats for this session."""
        return self._session_usage

    def reset_session_usage(self) -> None:
        """Reset session usage counters to zero."""
        self._session_usage = UsageStats()
        self._last_usage = None
        self._call_count = 0

    def print_usage_summary(self) -> None:
        """Pretty-print session usage summary with Rich."""
        u = self._session_usage
        self.console.print(
            f"\nSession Usage Summary ({self._call_count} calls):\n"
            f"  Total Tokens: {u.prompt_tokens:,} in / {u.completion_tokens:,} out / {u.total_tokens:,} total\n"
            f"  Total Cost: ${u.input_cost:.4f} in / ${u.output_cost:.4f} out / ${u.total_cost:.4f} total\n"
        )


def validate_model(model: str) -> GeminiModel:
    """Validate model name and return the corresponding GeminiModel enum.

    Args:
        model: Model name string to validate

    Returns:
        GeminiModel enum member

    Raises:
        ValueError: If model is not in available models
    """
    for m in GeminiModel:
        if m.model_name == model:
            return m
    names = ", ".join(m.model_name for m in GeminiModel)
    raise ValueError(f"Invalid model '{model}'. Available models: {names}")


def select_model_interactive(default: GeminiModel = DEFAULT_MODEL) -> GeminiModel:
    """Interactively select a Gemini model using Rich TUI.

    Displays available models and allows user to select one by entering a number.

    Args:
        default: Default model to preselect

    Returns:
        Selected GeminiModel enum member
    """
    console = Console()
    models = list(GeminiModel)

    console.print("\n[bold cyan]Select Gemini Model:[/bold cyan]\n")

    for idx, model in enumerate(models, 1):
        default_marker = " [green](default)[/green]" if model is default else ""
        console.print(f"  [cyan]{idx}[/cyan]. {model.model_name}{default_marker}")

    console.print()

    while True:
        choice = Prompt.ask(
            "Enter model number or press Enter for default",
            default=str(models.index(default) + 1),
            show_default=False,
        )

        try:
            choice_num = int(choice)
            if 1 <= choice_num <= len(models):
                selected = models[choice_num - 1]
                console.print(f"\n[green]✓ Selected: {selected.model_name}[/green]\n")
                return selected
            console.print(f"[red]Please enter a number between 1 and {len(models)}[/red]")
        except ValueError:
            console.print(f"[red]Invalid input. Please enter a number between 1 and {len(models)}[/red]")
