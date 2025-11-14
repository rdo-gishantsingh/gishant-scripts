# Gemini AI Common Utilities

This module provides reusable utilities for working with Google Gemini AI across the gishant-scripts project.

## Features

- **GeminiClient**: A wrapper class for the Google Gemini API with progress indicators
- **Model Selection**: Pre-configured list of available Gemini models
- **Interactive Selection**: Rich TUI for selecting models interactively
- **Validation**: Model name validation utilities

## Available Models

- `gemini-2.5-flash` (default) - Fast, efficient model for quick responses
- `gemini-2.5-pro` - More capable model for complex tasks
- `gemini-2.0-flash-exp` - Experimental flash model

## Usage Examples

### Basic Usage with GeminiClient

```python
from gishant_scripts.common.gemini import GeminiClient, DEFAULT_MODEL

# Initialize client
client = GeminiClient(api_key="your-api-key", model=DEFAULT_MODEL)

# Generate content
prompt = "Analyze this code and suggest improvements..."
response = client.generate_content(prompt, show_progress=True)
print(response)
```

### Interactive Model Selection

```python
from gishant_scripts.common.gemini import select_model_interactive

# Let user select a model interactively
selected_model = select_model_interactive(default="gemini-2.5-flash")
print(f"User selected: {selected_model}")
```

Output:
```
Select Gemini Model:

  1. gemini-2.5-flash (default)
  2. gemini-2.5-pro
  3. gemini-2.0-flash-exp

Enter model number or press Enter for default [1]: 2

✓ Selected: gemini-2.5-pro
```

### Using in CLI Applications

```python
import click
from gishant_scripts.common.gemini import AVAILABLE_MODELS, DEFAULT_MODEL, GeminiClient

@click.command()
@click.option(
    "--model",
    type=click.Choice(AVAILABLE_MODELS, case_sensitive=False),
    default=DEFAULT_MODEL,
    help="Gemini model to use",
)
def my_command(model: str):
    client = GeminiClient(api_key="your-api-key", model=model)
    result = client.generate_content("Your prompt here")
    print(result)
```

### Model Validation

```python
from gishant_scripts.common.gemini import validate_model, AVAILABLE_MODELS

try:
    model = validate_model("gemini-2.5-pro")
    print(f"Valid model: {model}")
except ValueError as e:
    print(f"Invalid model: {e}")
```

## Integration in Existing Tools

The following tools have been refactored to use this common module:

- `generate_copilot_prompt.py` - Generates GitHub Copilot prompts from YouTrack issues
- `generate_work_summary.py` - Generates work summaries from YouTrack issues

Both tools now share:
- Common model definitions
- Consistent API usage patterns
- Unified progress indicators
- Validation logic

## API Reference

### GeminiClient

```python
class GeminiClient:
    def __init__(self, api_key: str, model: str = DEFAULT_MODEL)
    def generate_content(self, prompt: str, *, show_progress: bool = True) -> str
```

### Functions

```python
def select_model_interactive(default: str = DEFAULT_MODEL) -> str
def validate_model(model: str) -> str
```

### Constants

```python
AVAILABLE_MODELS: list[str]  # List of available model names
DEFAULT_MODEL: str            # Default model name (gemini-2.5-flash)
```

## Benefits of This Approach

1. **DRY Principle**: Single source of truth for Gemini integration
2. **Consistency**: All tools use the same API patterns and error handling
3. **Maintainability**: Changes to Gemini API only need updates in one place
4. **User Experience**: Consistent progress indicators and error messages
5. **Flexibility**: Easy to add new models or change defaults
6. **Type Safety**: Full type hints for better IDE support

## Future Enhancements

Potential improvements could include:

- Support for streaming responses
- Token usage tracking and reporting
- Caching of responses
- Retry logic with exponential backoff
- Support for system instructions/prompts
- Temperature and other generation parameters
