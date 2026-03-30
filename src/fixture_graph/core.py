"""Core logic for parsing and rendering pytest setup plans as Graphviz diagrams."""

from __future__ import annotations

import dataclasses
import html
import logging
import pathlib
import re
from collections import defaultdict
from typing import NamedTuple

import pydantic

log = logging.getLogger(pathlib.Path(__file__).stem)

_FIXTURE_LINE = re.compile(r"^\s*SETUP\s+\S\s+(.+?)(?: \(fixtures used: (.*)\))?$")
_TEST_LINE = re.compile(r"^\s*(tests/[^\s]+::[^\s]+) \(fixtures used: (.*)\)$")

BUILTIN_FIXTURES = frozenset({"request", "tmp_path", "tmp_path_factory"})
DEFAULT_EXCLUDE_FIXTURES = frozenset({"tmp_path_factory"})


class Config(pydantic.BaseModel):
    """Configuration for fixture graph rendering."""

    model_config = pydantic.ConfigDict(frozen=True)

    exclude_fixtures: frozenset[str] = DEFAULT_EXCLUDE_FIXTURES
    parametrize_display: str = "highlight"  # "hide" | "show" | "highlight"


@dataclasses.dataclass(frozen=True)
class FixtureSetup:
    """A parsed fixture setup line."""

    name: str
    dependencies: tuple[str, ...]
    is_parametrized: bool = False  # True if from @pytest.mark.parametrize

    def __str__(self) -> str:
        """Return a compact summary of the fixture setup."""
        if not self.dependencies:
            return self.name
        return f"{self.name} <- {', '.join(self.dependencies)}"


@dataclasses.dataclass(frozen=True)
class ParsedTestCase:
    """A parsed test case line."""

    node_id: str
    test_file: str
    fixtures: tuple[str, ...]

    def __str__(self) -> str:
        """Return a compact summary of the test case."""
        if not self.fixtures:
            return self.node_id
        return f"{self.node_id} ({', '.join(self.fixtures)})"

    @property
    def name(self) -> str:
        """Return the pytest node name without the file prefix."""
        return self.node_id.split("::", 1)[1]

    def pattern_key(
        self,
        fixture_graph: FixtureGraph,
        cache: dict[str, frozenset[str]],
    ) -> PatternKey:
        """Build the grouping key used by the condensed graph."""
        # Filter to only non-excluded fixtures
        all_fixtures = tuple(
            f for f in self.fixtures if f not in fixture_graph.config.exclude_fixtures
        )
        return PatternKey(
            test_file=self.test_file,
            terminal_fixtures=_terminal_fixtures(self.fixtures, fixture_graph, cache),
            all_fixtures=all_fixtures,
        )


type SetupPlanEntry = FixtureSetup | ParsedTestCase
"""A parsed setup-plan line, either fixture setup or test case usage."""


@dataclasses.dataclass(frozen=True)
class FixtureGraph:
    """The fixture dependency graph."""

    dependencies_by_fixture: dict[str, frozenset[str]]
    config: Config
    parametrized_fixtures: frozenset[str] = (
        frozenset()
    )  # Fixtures from @pytest.mark.parametrize

    @property
    def names(self) -> tuple[str, ...]:
        """Return fixture names in stable order."""
        return tuple(sorted(self.dependencies_by_fixture))

    def dependencies(self, fixture: str) -> frozenset[str]:
        """Return the direct dependencies of a fixture."""
        return self.dependencies_by_fixture.get(fixture, frozenset())

    def render_cluster(self) -> list[str]:
        """Render the fixture subgraph."""
        lines = [
            "  subgraph cluster_fixtures {",
            '    label="Fixtures";',
            '    color="#94a3b8";',
            '    style="rounded";',
        ]
        for fixture_name in self.names:
            lines.append(self.render_fixture_node(fixture_name))
        lines.append("  }")
        return lines

    def render_fixture_node(self, fixture_name: str) -> str:
        """Render a single fixture node."""
        return (
            f"    {_node_id('fixture', fixture_name)} "
            f"[{self._dot_attributes(fixture_name)} "
            f'label="{_dot_label(fixture_name)}"];'
        )

    def render_dependency_edges(self) -> list[str]:
        """Render edges between fixture nodes."""
        lines: list[str] = []
        for fixture_name, deps in sorted(self.dependencies_by_fixture.items()):
            for dep in deps:
                if dep not in self.dependencies_by_fixture:
                    continue
                lines.append(
                    f"  {_node_id('fixture', dep)} -> {_node_id('fixture', fixture_name)};"
                )
        return lines

    def _dot_attributes(self, name: str) -> str:
        """Return Graphviz attributes for a fixture node.

        Color scheme:
        - Gray: Built-in fixtures (request, tmp_path, tmp_path_factory)
        - Yellow: Excluded fixtures
        - Green: Parametrized fixtures (only if parametrize_display="highlight")
        - Blue: Custom fixtures
        """
        if name in BUILTIN_FIXTURES:
            return 'shape=box style="rounded,filled" fillcolor="#e5e7eb"'
        if name in self.config.exclude_fixtures:
            return 'shape=box style="rounded,filled" fillcolor="#fde68a"'
        if (
            name in self.parametrized_fixtures
            and self.config.parametrize_display == "highlight"
        ):
            return 'shape=box style="rounded,filled" fillcolor="#bbf7d0"'  # Light green
        return 'shape=box style="rounded,filled" fillcolor="#bfdbfe"'


@dataclasses.dataclass(frozen=True)
class SetupPlan:
    """The parsed pytest setup plan."""

    fixtures: FixtureGraph
    tests: tuple[ParsedTestCase, ...]
    config: Config

    @classmethod
    def parse(cls, text: str, config: Config) -> SetupPlan:
        """Parse raw ``pytest --setup-plan`` output."""
        lines = text.splitlines()
        log.debug("parsing %d lines of setup-plan output", len(lines))
        entries = tuple(
            entry for line in lines if (entry := parse_entry(line)) is not None
        )
        log.debug("parsed %d entries from setup-plan", len(entries))
        return cls._from_entries(entries, config)

    @classmethod
    def _from_entries(
        cls,
        entries: tuple[SetupPlanEntry, ...],
        config: Config,
    ) -> SetupPlan:
        """Build a setup plan from parsed entries."""
        exclude = config.exclude_fixtures
        fixture_deps: dict[str, set[str]] = defaultdict(set)
        parametrized: set[str] = set()
        tests: list[ParsedTestCase] = []

        for entry in entries:
            if isinstance(entry, FixtureSetup):
                if entry.name in exclude:
                    log.debug("excluding fixture: %s", entry.name)
                    continue
                # Handle parametrize_display config
                if entry.is_parametrized:
                    parametrized.add(entry.name)
                    if config.parametrize_display == "hide":
                        log.debug("hiding parametrized fixture: %s", entry.name)
                        continue
                fixture_deps.setdefault(entry.name, set())
                fixture_deps[entry.name].update(
                    dependency
                    for dependency in entry.dependencies
                    if dependency not in exclude
                )
                continue
            tests.append(entry)

        log.info(
            "built graph with %d fixtures and %d tests (%d parametrized)",
            len(fixture_deps),
            len(tests),
            len(parametrized),
        )
        return cls(
            fixtures=FixtureGraph(
                dependencies_by_fixture={
                    fixture_name: frozenset(sorted(dependencies))
                    for fixture_name, dependencies in fixture_deps.items()
                },
                config=config,
                parametrized_fixtures=frozenset(parametrized),
            ),
            tests=tuple(tests),
            config=config,
        )

    def render_dot(self) -> str:
        """Render the full condensed DOT graph."""
        grouped_tests = self.group_test_patterns()
        log.debug(
            "rendering DOT graph: %d test file(s), %d fixture(s)",
            len(grouped_tests),
            len(self.fixtures.names),
        )
        lines = [
            "digraph pytest_setup_plan {",
            '  graph [rankdir=LR, fontname="Helvetica", fontsize=10, labelloc=t, '
            'label="Pytest setup-plan graph (condensed)"];',
            '  node [fontname="Helvetica", fontsize=10];',
            '  edge [fontname="Helvetica", fontsize=9, color="#475569"];',
            "",
        ]
        lines.extend(self.fixtures.render_cluster())
        lines.append("")
        lines.extend(self.fixtures.render_dependency_edges())
        lines.append("")

        for test_file, patterns in sorted(grouped_tests.items()):
            lines.extend(self.render_test_cluster(test_file, patterns))
            lines.append("")

        lines.append("}")
        return "\n".join(lines)

    def group_test_patterns(self) -> dict[str, tuple[Pattern, ...]]:
        """Group tests by file and terminal fixture set."""
        grouped: dict[str, dict[PatternKey, list[str]]] = defaultdict(
            lambda: defaultdict(list)
        )
        cache: dict[str, frozenset[str]] = {}

        for test_case in self.tests:
            grouped[test_case.test_file][
                test_case.pattern_key(self.fixtures, cache)
            ].append(test_case.name)

        return {
            test_file: tuple(
                Pattern(key=pattern_key, test_names=tuple(test_names))
                for pattern_key, test_names in sorted(patterns.items())
            )
            for test_file, patterns in grouped.items()
        }

    def render_test_cluster(
        self, test_file: str, patterns: tuple[Pattern, ...]
    ) -> list[str]:
        """Render one per-file test cluster."""
        cluster_name = _node_id("cluster", test_file)
        lines = [
            f"  subgraph {cluster_name} {{",
            f'    label="{_dot_label(test_file)}";',
            '    color="#cbd5e1";',
            '    style="rounded";',
        ]
        for index, pattern in enumerate(patterns, start=1):
            lines.extend(pattern.render_dot(index, self.fixtures))
        lines.append("  }")
        return lines


class PatternKey(NamedTuple):
    """The grouping key for condensed test nodes."""

    test_file: str
    terminal_fixtures: tuple[str, ...]
    all_fixtures: tuple[str, ...] = ()  # All fixtures used (for rendering edges)

    def fixture_summary(self) -> str:
        """Summarize the terminal fixtures for display."""
        if self.terminal_fixtures:
            return ", ".join(self.terminal_fixtures)
        return "no explicit non-builtin fixture"


@dataclasses.dataclass(frozen=True)
class Pattern:
    """A condensed group of tests sharing the same terminal fixtures."""

    key: PatternKey
    test_names: tuple[str, ...]

    @property
    def count(self) -> int:
        """Return the number of grouped tests."""
        return len(self.test_names)

    def render_dot(self, index: int, fixture_graph: FixtureGraph) -> list[str]:
        """Render one condensed test-pattern node and its edges."""
        node_name = _node_id("test", f"{self.key.test_file}_{index}")
        lines = [
            f'    {node_name} [shape=note, style="filled", fillcolor="#f8fafc", '
            f"label=<{_html_label(self.label_lines())}>];"
        ]
        # Render edges from fixtures that are in the graph and actually used by this test
        for fixture in sorted(self.key.all_fixtures):
            if fixture not in fixture_graph.dependencies_by_fixture:
                continue
            lines.append(
                f"    {_node_id('fixture', fixture)} -> {node_name} "
                '[style=dashed, color="#0f766e"];'
            )
        return lines

    def label_lines(self) -> tuple[str, ...]:
        """Build the node label lines for the condensed test pattern."""
        return (
            pathlib.Path(self.key.test_file).name,
            f"{self.count} test(s)",
            *self.test_names,
            self.key.fixture_summary(),
        )


def normalize_fixture_name(name: str) -> str:
    """Strip pytest parameter suffixes from a fixture name."""
    return name.split("[", 1)[0]


def is_parametrized_fixture(name: str) -> bool:
    """Check if a fixture name indicates parametrization (has brackets with values)."""
    return "[" in name and "]" in name


def parse_fixture_list(raw: str) -> tuple[str, ...]:
    """Parse a comma-separated fixture list."""
    return tuple(
        normalize_fixture_name(fixture.strip())
        for fixture in raw.split(",")
        if fixture.strip()
    )


def parse_entry(line: str) -> SetupPlanEntry | None:
    """Parse one setup-plan line into a typed entry."""
    fixture_match = _FIXTURE_LINE.match(line)
    if fixture_match:
        raw_name = fixture_match.group(1)
        return FixtureSetup(
            name=normalize_fixture_name(raw_name),
            dependencies=parse_fixture_list(fixture_match.group(2) or ""),
            is_parametrized=is_parametrized_fixture(raw_name),
        )

    test_match = _TEST_LINE.match(line)
    if test_match:
        node_id = test_match.group(1)
        return ParsedTestCase(
            node_id=node_id,
            test_file=node_id.split("::", 1)[0],
            fixtures=parse_fixture_list(test_match.group(2)),
        )

    return None


def _ancestors(
    fixture: str,
    fixture_graph: FixtureGraph,
    cache: dict[str, frozenset[str]],
) -> frozenset[str]:
    """Return all transitive dependencies of a fixture."""
    if fixture in cache:
        return cache[fixture]

    result: set[str] = set()
    for dep in fixture_graph.dependencies(fixture):
        result.add(dep)
        result.update(_ancestors(dep, fixture_graph, cache))

    cache[fixture] = frozenset(result)
    return cache[fixture]


def _terminal_fixtures(
    fixtures: tuple[str, ...],
    fixture_graph: FixtureGraph,
    cache: dict[str, frozenset[str]],
) -> tuple[str, ...]:
    """Keep only non-builtin fixtures that are not implied by others."""
    active_fixtures = tuple(
        fixture
        for fixture in fixtures
        if fixture not in BUILTIN_FIXTURES
        and fixture not in fixture_graph.config.exclude_fixtures
    )
    terminal_fixtures: list[str] = []
    for fixture in active_fixtures:
        if any(
            fixture != other and fixture in _ancestors(other, fixture_graph, cache)
            for other in active_fixtures
        ):
            continue
        terminal_fixtures.append(fixture)
    return tuple(sorted(set(terminal_fixtures)))


def _node_id(prefix: str, raw: str) -> str:
    """Build a stable Graphviz-safe node identifier."""
    sanitized = re.sub(r"[^A-Za-z0-9_]+", "_", raw)
    return f"{prefix}_{sanitized}".strip("_")


def _dot_label(text: str) -> str:
    """Escape text for use in a DOT label."""
    return text.replace("\\", "\\\\").replace('"', '\\"')


def _html_label(lines: tuple[str, ...]) -> str:
    """Render label lines as a Graphviz HTML label."""
    return '<BR ALIGN="LEFT"/>'.join(html.escape(line) for line in lines)
