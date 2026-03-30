"""Tests for fixture_graph.cli module."""

import json
import pathlib

import pydantic
import pytest

from fixture_graph.cli import CliArgs, format_validation_error, load_config
from fixture_graph.core import DEFAULT_EXCLUDE_FIXTURES, Config


def test_load_config_defaults() -> None:
    """Test loading default config when no file provided."""
    config = load_config(None)
    assert config.exclude_fixtures == DEFAULT_EXCLUDE_FIXTURES


def test_load_config_from_file(tmp_path: pathlib.Path) -> None:
    """Test loading config from a JSON file."""
    config_file = tmp_path / "config.json"
    config_file.write_text(
        json.dumps(
            {
                "exclude_fixtures": [
                    "tmp_path_factory",
                    "shell",
                    "db",
                ]
            }
        )
    )
    config = load_config(config_file)
    assert config.exclude_fixtures == frozenset({"tmp_path_factory", "shell", "db"})


def test_load_config_missing_key_uses_defaults(tmp_path: pathlib.Path) -> None:
    """Test that missing exclude_fixtures key falls back to defaults."""
    config_file = tmp_path / "config.json"
    config_file.write_text(json.dumps({"other_key": []}))
    config = load_config(config_file)
    assert config.exclude_fixtures == DEFAULT_EXCLUDE_FIXTURES


def test_load_config_nonexistent_file() -> None:
    """Test that a missing file produces a readable OS error."""
    with pytest.raises(SystemExit, match="cannot read config file"):
        load_config(pathlib.Path("/nonexistent/config.json"))


@pytest.mark.parametrize(
    ("content", "expected_fragment"),
    [
        pytest.param(
            "{ invalid json }",
            "Invalid JSON",
            id="malformed-json",
        ),
        pytest.param(
            json.dumps({"exclude_fixtures": "not a list"}),
            "exclude_fixtures: Input should be a valid",
            id="wrong-type-string",
        ),
        pytest.param(
            json.dumps({"exclude_fixtures": [1, 2]}),
            "exclude_fixtures.0: Input should be a valid string",
            id="wrong-element-type",
        ),
        pytest.param(
            json.dumps({"exclude_fixtures": {"a": "b"}}),
            "exclude_fixtures: Input should be a valid",
            id="wrong-type-dict",
        ),
    ],
)
def test_load_config_validation_error(
    tmp_path: pathlib.Path, content: str, expected_fragment: str
) -> None:
    """Test that invalid configs produce human-friendly error messages."""
    config_file = tmp_path / "config.json"
    config_file.write_text(content)
    with pytest.raises(SystemExit, match="error: invalid config file"):
        load_config(config_file)
    # Also verify the specific fragment appears in the formatted message
    try:
        load_config(config_file)
    except SystemExit as e:
        assert expected_fragment in str(e)


def test_format_validation_error_single_error() -> None:
    """Test formatting a single validation error."""
    with pytest.raises(pydantic.ValidationError) as exc_info:
        Config.model_validate_json('{"exclude_fixtures": "bad"}')
    result = format_validation_error(pathlib.Path("test.json"), exc_info.value)
    assert result.startswith("error: invalid config file test.json")
    assert "\n  exclude_fixtures:" in result


def test_format_validation_error_multiple_errors() -> None:
    """Test formatting multiple validation errors."""
    with pytest.raises(pydantic.ValidationError) as exc_info:
        Config.model_validate_json('{"exclude_fixtures": [1, 2]}')
    result = format_validation_error(pathlib.Path("test.json"), exc_info.value)
    lines = result.splitlines()
    assert lines[0] == "error: invalid config file test.json"
    # One line per invalid element (2 items = 2 errors)
    error_lines = [line for line in lines if line.startswith("  ")]
    expected_error_count = 2
    assert len(error_lines) == expected_error_count


def test_format_validation_error_root_error() -> None:
    """Test formatting an error at the root level (invalid JSON)."""
    with pytest.raises(pydantic.ValidationError) as exc_info:
        Config.model_validate_json("not json")
    result = format_validation_error(pathlib.Path("bad.json"), exc_info.value)
    assert "(root):" in result


def test_cli_args_creation() -> None:
    """Test creating CliArgs instance."""
    args = CliArgs(
        input=pathlib.Path("input.txt"),
        cwd=pathlib.Path("."),
        output_prefix=pathlib.Path("output"),
        config=None,
    )
    assert args.input == pathlib.Path("input.txt")
    assert args.cwd == pathlib.Path(".")
    assert args.output_prefix == pathlib.Path("output")
    assert args.config is None
