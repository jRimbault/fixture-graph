## Development Setup

Clone the repository and install with development dependencies:

```bash
git clone <repository-url>
cd fixture-graph
uv sync --all-groups
```

## Running Tests

```bash
uv run pytest
```

For coverage:

```bash
uv run pytest --cov=fixture_graph
```

## Code Quality

This project uses:
- **ruff** for formatting and linting
- **pyright** for type checking

Check code quality:

```bash
uv run ruff check .
uv run pyright
```

Auto-format code:

```bash
uv run ruff format .
```
