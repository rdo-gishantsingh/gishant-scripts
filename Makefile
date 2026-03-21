.PHONY: help install dev sync format lint test clean

help: ## Show this help message
	@echo 'Usage: make [target]'
	@echo ''
	@echo 'Available targets:'
	@awk 'BEGIN {FS = ":.*?## "} /^[a-zA-Z_-]+:.*?## / {printf "  %-15s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

install: ## Install dependencies using uv
	uv sync

dev: ## Install with development dependencies
	uv sync --extra dev

sync: ## Sync dependencies (update lock file)
	uv sync --upgrade

format: ## Format code with ruff
	uv run ruff format src/ tests/

lint: ## Lint code with ruff
	uv run ruff check src/ tests/ --fix

lint-check: ## Check linting without fixing
	uv run ruff check src/ tests/

test: ## Run tests with pytest
	uv run pytest tests/ -v

test-unit: ## Run unit tests only
	uv run pytest tests/unit/ -v

test-integration: ## Run integration tests only
	uv run pytest tests/ -m integration -v

test-all: ## Run all tests (ignore addopts overrides)
	uv run pytest tests/ -v --override-ini="addopts="

test-cov: ## Run tests with coverage
	uv run pytest tests/ -v --cov=src/gishant_scripts --cov-report=html --cov-report=term

clean: ## Clean build artifacts and cache files
	@echo "Cleaning build artifacts..."
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name "htmlcov" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@find . -type f -name ".coverage" -delete 2>/dev/null || true
	@rm -rf build/ dist/ 2>/dev/null || true
	@echo "Clean complete."

all: clean install lint test ## Run full CI pipeline
