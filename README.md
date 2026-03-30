# fixture-graph

Render `pytest --setup-plan` output as a condensed Graphviz diagram.

This tool parses pytest's setup plan output and generates a visual graph showing fixture dependencies and test usage patterns. It helps you understand and debug complex fixture hierarchies.

## Installation

Install using `uv`:

```bash
uv tool install fixture-graph
```

## Usage

### Basic Usage

Generate a graph from your current project's pytest setup plan:

```bash
fixture-graph --output-prefix ./artifacts/setup-plan
```

This will create:
- `artifacts/setup-plan.dot` - Graphviz DOT format
- `artifacts/setup-plan.svg` - Rendered SVG (if Graphviz is installed)

### Reading from a File

If you have existing setup plan output:

```bash
fixture-graph --input setup-plan.txt --output-prefix ./output/graph
```

### Custom Working Directory

To run pytest in a different directory:

```bash
fixture-graph --cwd /path/to/project --output-prefix ./output/graph
```

### Configuration File

Some fixtures can be excluded from the graph or displayed differently. Configure this with a JSON file:

```bash
fixture-graph --config config.json --output-prefix ./output/graph
```

**config.json:**
```json
{
  "exclude_fixtures": [
    "tmp_path_factory",
    "shell",
    "action",
    "state",
    "expected_state"
  ],
  "parametrize_display": "highlight"
}
```

**Options:**

- `exclude_fixtures`: List of fixture names to exclude from the graph entirely.
- `parametrize_display`: How to display fixtures from `@pytest.mark.parametrize`:
  - `"hide"`: Don't show parametrized fixtures in the graph
  - `"show"`: Show parametrized fixtures in blue (same as custom fixtures)
  - `"highlight"`: Show parametrized fixtures in green (default)

## Requirements

- Python 3.12+
- `pytest` (for generating setup plans)
- `graphviz` (optional, for SVG rendering; `dot` binary must be in PATH)

## Graph Interpretation

The generated graph shows:

- **Blue boxes**: Custom fixtures (or parametrized fixtures in "show" mode)
- **Green boxes**: Parametrized fixtures from `@pytest.mark.parametrize` (in "highlight" mode)
- **Gray boxes**: Built-in pytest fixtures (request, tmp_path, tmp_path_factory)
- **Solid arrows**: Fixture dependency relationships
- **Dashed arrows**: Test usage of fixtures
- **Test nodes**: Grouped by file and shared fixture patterns

## Development

Clone the repository and install with development dependencies:

```bash
git clone <repository-url>
cd fixture-graph
uv sync --all-groups
```

Run tests:

```bash
uv run pytest
```

Run linting:

```bash
uv run ruff check .
uv run ruff format .
uv run pyright
```

## License

MIT
