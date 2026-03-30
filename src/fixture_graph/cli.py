"""Command-line interface for pytest setup plan rendering.

This tool parses pytest's setup plan output and generates a visual graph showing
fixture dependencies and test usage patterns.
It helps understand and debug complex fixture hierarchies.
"""

from __future__ import annotations

import dataclasses
import logging
import pathlib
import shutil
import subprocess
import sys

import pydantic
import tyro
from typing_extensions import Annotated

from .core import Config, SetupPlan
from .verbosity import Verbosity

log = logging.getLogger(pathlib.Path(__file__).stem)


@dataclasses.dataclass(frozen=True)
class CliArgs:
    """Render pytest setup plan as a condensed Graphviz graph."""

    input: pathlib.Path | None = None
    """Read setup-plan output from a file instead of running pytest."""
    cwd: pathlib.Path = dataclasses.field(default_factory=lambda: pathlib.Path("."))
    """Repository directory used when invoking pytest."""
    output_prefix: pathlib.Path = dataclasses.field(
        default_factory=lambda: pathlib.Path(".") / "artifacts/fixture-graph"
    )
    """Output path prefix for the generated .dot and .svg files."""
    config: pathlib.Path | None = None
    """Configuration file with exclude_fixtures list (JSON format)."""
    verbosity: Annotated[Verbosity, tyro.conf.OmitArgPrefixes] = dataclasses.field(
        default_factory=Verbosity
    )
    """Control log verbosity with -v (verbose) or -q (quiet)."""


def main() -> int:
    """Parse CLI arguments and run the renderer."""
    args = tyro.cli(CliArgs)
    logging.basicConfig(level=args.verbosity.log_level())
    return run(args)


def run(args: CliArgs) -> int:
    """Generate DOT and SVG artifacts for a setup plan."""
    config = load_config(args.config)
    setup_plan = SetupPlan.parse(read_input(args), config)
    dot_output = setup_plan.render_dot()

    output_prefix = args.output_prefix
    output_prefix.parent.mkdir(parents=True, exist_ok=True)
    dot_path = output_prefix.with_suffix(".dot")
    svg_path = output_prefix.with_suffix(".svg")
    dot_path.write_text(dot_output)
    log.info("wrote %s", dot_path)

    dot_binary = shutil.which("dot")
    if dot_binary is None:
        log.warning("graphviz 'dot' not found in PATH, skipping SVG render")
        print(f"Wrote {dot_path}")
        return 0

    log.debug("running %s -Tsvg %s -o %s", dot_binary, dot_path, svg_path)
    subprocess.run(
        [dot_binary, "-Tsvg", str(dot_path), "-o", str(svg_path)],
        check=True,
    )
    log.info("wrote %s", svg_path)
    print(f"Wrote {dot_path}")
    print(f"Wrote {svg_path}")
    return 0


def read_input(args: CliArgs) -> str:
    """Load setup-plan text from a file or by running pytest."""
    if args.input is not None:
        log.info("reading setup plan from %s", args.input)
        return args.input.read_text()

    log.info("running pytest --setup-plan in %s", args.cwd.resolve())
    result = subprocess.run(
        ["pytest", "--setup-plan"],
        capture_output=True,
        text=True,
        check=False,
        cwd=args.cwd,
    )
    if result.returncode != 0:
        log.error("pytest exited with code %d", result.returncode)
        sys.stderr.write(result.stdout)
        sys.stderr.write(result.stderr)
        raise SystemExit(result.returncode)
    return result.stdout


def load_config(config_path: pathlib.Path | None) -> Config:
    """Load config from a JSON file, or return defaults."""
    if config_path is None:
        log.debug("no config file, using defaults")
        return Config()

    log.info("loading config from %s", config_path)
    try:
        return Config.model_validate_json(config_path.read_bytes())
    except OSError as e:
        raise SystemExit(
            f"error: cannot read config file {config_path}: {e.strerror}"
        ) from e
    except pydantic.ValidationError as e:
        raise SystemExit(format_validation_error(config_path, e)) from e


def format_validation_error(path: pathlib.Path, error: pydantic.ValidationError) -> str:
    """Format a pydantic ValidationError into a human-friendly message."""
    lines = [f"error: invalid config file {path}"]
    for err in error.errors():
        loc = ".".join(str(part) for part in err["loc"]) if err["loc"] else "(root)"
        lines.append(f"  {loc}: {err['msg']}")
    return "\n".join(lines)
